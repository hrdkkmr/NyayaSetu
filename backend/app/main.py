"""FastAPI application factory."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.api import admin, auth, cases, documents, drafts, legal, notifications, users, voice
from app.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_sessionmaker

logger = logging.getLogger(__name__)
API_PREFIX = "/api/v1"


def _init_observability(app: FastAPI) -> None:
    s = get_settings()
    if s.sentry_dsn:
        import sentry_sdk

        # send_default_pii=False: never ship request bodies, cookies or user details to Sentry.
        def _scrub(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
            # Stack-frame locals and breadcrumbs could contain transcripts or document text.
            for exc in (event.get("exception") or {}).get("values", []):
                for frame in (exc.get("stacktrace") or {}).get("frames", []):
                    frame.pop("vars", None)
            event.pop("breadcrumbs", None)
            event.pop("request", None)
            return event

        sentry_sdk.init(dsn=s.sentry_dsn, environment=s.environment, traces_sample_rate=0.1,
                        send_default_pii=False, include_local_variables=False,
                        max_request_body_size="never", before_send=_scrub)  # type: ignore[arg-type]
    if s.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider(resource=Resource.create({"service.name": "nyayasetu-api"}))
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=s.otel_exporter_otlp_endpoint)))
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
        except ImportError:
            logger.warning("OTEL endpoint set but the OTLP exporter package is not installed")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    if s.is_production:
        problems = s.validate_for_production()
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level)
    app = FastAPI(
        title="NyayaSetu API", version=__version__, lifespan=lifespan,
        docs_url=None if s.is_production else "/api/docs",
        openapi_url=None if s.is_production else "/api/openapi.json",
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization", "X-Client-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        if request.url.path.startswith(API_PREFIX):
            response.headers.setdefault("Cache-Control", "no-store")
        if s.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    api = APIRouter(prefix=API_PREFIX)
    for module in (auth, users, cases, documents, drafts, legal, notifications, admin, voice):
        api.include_router(module.router)
    app.include_router(api)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> Response:
        try:
            async with get_sessionmaker()() as db:
                await db.execute(text("SELECT 1"))
            return Response('{"status":"ready"}', media_type="application/json")
        except Exception:  # noqa: BLE001
            return Response('{"status":"database_unavailable"}', media_type="application/json", status_code=503)

    _init_observability(app)
    return app


app = create_app()
