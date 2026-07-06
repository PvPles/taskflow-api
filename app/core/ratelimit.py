"""Per-user rate limiting via a token bucket.

Buckets live in process memory: right-sized for a single-instance deployment
(this app's target). Scaling to multiple instances would move the buckets to
Redis; the interface below would not change.
"""

import math
import time

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import get_settings
from app.core.errors import error_response
from app.core.security import decode_access_token

EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class TokenBucket:
    """Classic token bucket: `capacity` requests of burst, refilled at
    `refill_per_sec` tokens per second."""

    __slots__ = ("capacity", "refill_per_sec", "tokens", "updated")

    def __init__(self, capacity: int, refill_per_sec: float, now: float):
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = float(capacity)
        self.updated = now

    def allow(self, now: float) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        elapsed = max(0.0, now - self.updated)
        self.tokens = min(float(self.capacity), self.tokens + elapsed * self.refill_per_sec)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0
        if self.refill_per_sec <= 0:
            return False, 60
        return False, math.ceil((1.0 - self.tokens) / self.refill_per_sec)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._buckets: dict[str, TokenBucket] = {}

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.rate_limit_enabled or request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = self._buckets[key] = TokenBucket(
                settings.rate_limit_burst, settings.rate_limit_per_minute / 60.0, now
            )
        allowed, retry_after = bucket.allow(now)
        if not allowed:
            response = error_response(429, "rate_limited", "Too many requests, slow down")
            response.headers["Retry-After"] = str(retry_after)
            return response
        return await call_next(request)

    @staticmethod
    def _client_key(request: Request) -> str:
        """Authenticated requests are limited per user, anonymous ones per IP."""
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                payload = decode_access_token(auth[7:])
                return f"user:{payload['sub']}"
            except jwt.InvalidTokenError:
                pass
        host = request.client.host if request.client else "unknown"
        return f"ip:{host}"
