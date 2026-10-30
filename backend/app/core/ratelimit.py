"""Fixed-window rate limiting backed by Redis when available, memory otherwise."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request

from app.config import get_settings
from app.core.errors import RateLimitedError

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._lock = Lock()
        self._redis = None
        settings = get_settings()
        if settings.redis_url:
            try:
                from redis.asyncio import Redis

                self._redis = Redis.from_url(settings.redis_url)
            except Exception:  # noqa: BLE001 - any Redis client error falls back to memory
                logger.warning("Redis unavailable for rate limiting; using in-memory limiter")

    async def hit(self, bucket: str, limit: int, window_seconds: int = 60) -> None:
        window = int(time.time() // window_seconds)
        key = f"rl:{bucket}:{window}"
        if self._redis is not None:
            try:
                count = await self._redis.incr(key)
                if count == 1:
                    await self._redis.expire(key, window_seconds)
                if count > limit:
                    raise RateLimitedError("Too many requests. Please wait a minute and try again.")
                return
            except RateLimitedError:
                raise
            except Exception:  # noqa: BLE001 - degrade to in-memory limiting
                logger.warning("Redis rate limit check failed; falling back to memory")
        with self._lock:
            # Drop stale windows opportunistically to bound memory.
            if len(self._counts) > 50_000:
                self._counts.clear()
            self._counts[key] += 1
            count = self._counts[key]
        if count > limit:
            raise RateLimitedError("Too many requests. Please wait a minute and try again.")

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    # X-Forwarded-For is client-controlled. uvicorn's --proxy-headers rewrites request.client
    # only for proxies listed in FORWARDED_ALLOW_IPS, so this is the trustworthy address.
    return request.client.host if request.client else "unknown"


async def rate_limit_auth(request: Request) -> None:
    await limiter.hit(f"auth:{client_ip(request)}", get_settings().auth_rate_limit_per_minute)


async def rate_limit_account(email: str) -> None:
    """Per-account bucket so login/reset guessing can't be spread across many IPs."""
    from app.core.security import keyed_hash

    await limiter.hit(f"auth:acct:{keyed_hash(email.lower(), 'rl')[:24]}",
                      get_settings().auth_rate_limit_per_minute)
