"""Integration health checks. Reports configuration honestly: 'not_configured' is a valid state."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import utcnow
from app.integrations import ejagriti
from app.integrations.speech import sarvam_configured
from app.models import IntegrationConfig, LegalDocument
from app.services.document_processing import ocr_available
from app.services.email import email_configured
from app.services.storage import get_storage


def _status(ok: bool | None, detail: str) -> dict[str, Any]:
    return {"status": "not_configured" if ok is None else ("ok" if ok else "error"), "detail": detail}


async def check_integrations(db: AsyncSession, include_external: bool = True) -> dict[str, dict[str, Any]]:
    s = get_settings()
    results: dict[str, dict[str, Any]] = {}
    try:
        await db.execute(text("SELECT 1"))
        results["database"] = _status(True, "PostgreSQL" if not s.is_sqlite else "SQLite (development only)")
    except Exception as exc:  # noqa: BLE001
        results["database"] = _status(False, type(exc).__name__)

    if s.redis_url:
        try:
            from redis.asyncio import Redis

            r = Redis.from_url(s.redis_url)
            await r.ping()
            await r.aclose()
            results["redis"] = _status(True, "reachable")
        except Exception as exc:  # noqa: BLE001
            results["redis"] = _status(False, type(exc).__name__)
    else:
        results["redis"] = _status(None, "REDIS_URL not set; jobs run in-process")

    ok, detail = await get_storage().health()
    results["storage"] = _status(ok, f"{get_storage().name}: {detail}")
    results["llm"] = _status(True if s.llm_configured else None,
                             s.llm_description if s.llm_configured else
                             "No LLM credentials set; rule-based agents are used")
    results["speech_sarvam"] = _status(True if sarvam_configured() else None,
                                       "configured" if sarvam_configured() else "SARVAM_API_KEY not set; browser speech only")
    results["ocr"] = _status(True if ocr_available() else None,
                             "Tesseract available" if ocr_available() else "Tesseract not installed; scanned files cannot be read")
    results["google_sign_in"] = _status(True if s.google_client_id else None,
                                        "configured" if s.google_client_id else "GOOGLE_CLIENT_ID not set; button hidden")
    results["email"] = _status(True if email_configured() else None,
                               "SMTP configured" if email_configured() else "SMTP not set; emails are not sent")
    caps = ejagriti.capabilities()
    results["browser_assist"] = _status(True if caps.browser_assist else None, "; ".join(caps.notes))

    docs = (await db.execute(select(LegalDocument.ingestion_status, func.count()).group_by(LegalDocument.ingestion_status))).all()
    counts = {status: n for status, n in docs}
    ingested = counts.get("ingested", 0) + counts.get("unchanged", 0)
    results["legal_knowledge_base"] = _status(ingested > 0 if docs else False,
                                              f"{ingested} document(s) ingested" if docs else "No legal sources ingested yet")
    if include_external:
        portal = await ejagriti.check_health()
        results["ejagriti_portal"] = _status(portal.get("reachable", False),
                                             f"HTTP {portal.get('status_code')} in {portal.get('latency_ms')} ms"
                                             if portal.get("reachable") else f"unreachable ({portal.get('error')})")

    for key, value in results.items():
        row = await db.scalar(select(IntegrationConfig).where(IntegrationConfig.key == key))
        if row is None:
            row = IntegrationConfig(key=key, enabled=True, settings={})
            db.add(row)
        row.last_check_at = utcnow()
        row.last_status = value["status"]
        row.last_detail = value["detail"]
    return results
