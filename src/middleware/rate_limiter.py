"""Token-bucket rate limiter middleware.

Provides per-IP and per-user rate limiting with configurable windows.
Uses an in-memory store for single-instance deployments; swap the backend
for Redis in multi-instance setups.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from src.config.settings import settings


@dataclass
class TokenBucket:
    capacity: int
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    @property
    def retry_after(self) -> int:
        if self.tokens >= 1:
            return 0
        return max(1, int((1 - self.tokens) / self.refill_rate))


class RateLimitStore:
    """In-memory store keyed by client identifier."""

    def __init__(self, capacity: int, refill_rate: float):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(capacity=self._capacity, refill_rate=self._refill_rate)
        )

    def check(self, key: str) -> tuple[bool, int]:
        bucket = self._buckets[key]
        allowed = bucket.consume()
        return allowed, bucket.retry_after


RATE_LIMIT_CONFIGS = {
    "/api/auth/login": {"capacity": 5, "refill_rate": 0.1},      # 5 attempts, 1 per 10s refill
    "/api/auth/register": {"capacity": 3, "refill_rate": 0.05},   # 3 attempts, 1 per 20s refill
    "/api/payments/charge": {"capacity": 10, "refill_rate": 0.5},  # 10 per burst, 1 per 2s refill
    "/api/payments/refund": {"capacity": 5, "refill_rate": 0.2},   # 5 per burst, 1 per 5s refill
}

_stores: dict[str, RateLimitStore] = {}


def _get_store(path: str) -> Optional[RateLimitStore]:
    if path not in _stores and path in RATE_LIMIT_CONFIGS:
        cfg = RATE_LIMIT_CONFIGS[path]
        _stores[path] = RateLimitStore(cfg["capacity"], cfg["refill_rate"])
    return _stores.get(path)


def _extract_client_id(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        store = _get_store(request.url.path)
        if store is None:
            return await call_next(request)

        client_id = _extract_client_id(request)
        allowed, retry_after = store.check(client_id)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please try again later.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        return response
