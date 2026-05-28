"""Rate Limiter Implementation.

Protection against abuse via Token Bucket algorithm.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TokenBucket:
    """Token Bucket for a specific client."""

    capacity: float
    refill_rate: float
    tokens: float = field(default=-1.0)
    last_update: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.tokens < 0:
            self.tokens = self.capacity

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume tokens. Returns True if available."""
        now = time.time()
        elapsed = now - self.last_update
        self.last_update = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def available_tokens(self) -> float:
        """Currently available tokens."""
        now = time.time()
        elapsed = now - self.last_update
        return min(self.capacity, self.tokens + elapsed * self.refill_rate)


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, key: str, retry_after: float) -> None:
        self.key = key
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for '{key}'. Retry after {retry_after:.1f}s")


class RateLimiter:
    """Rate Limiter with Token Bucket algorithm.

    Args:
        rate: Number of allowed requests.
        per: Period in seconds (default: 60).
        burst: Burst capacity (default: rate * 2).
    """

    def __init__(
        self,
        rate: int = 100,
        per: float = 60.0,
        burst: int | None = None,
        key_prefix: str = "",
    ) -> None:
        self.rate = rate
        self.per = per
        self.burst = burst or rate * 2
        self.key_prefix = key_prefix
        self.refill_rate = rate / per
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = Lock()
        self._stats = {
            "total_requests": 0,
            "allowed_requests": 0,
            "rejected_requests": 0,
        }

    def _get_bucket(self, key: str) -> TokenBucket:
        full_key = f"{self.key_prefix}{key}" if self.key_prefix else key
        with self._lock:
            if full_key not in self._buckets:
                self._buckets[full_key] = TokenBucket(
                    capacity=self.burst,
                    refill_rate=self.refill_rate,
                )
            return self._buckets[full_key]

    def allow(self, key: str, tokens: float = 1.0) -> bool:
        """Check if a request is allowed."""
        bucket = self._get_bucket(key)
        self._stats["total_requests"] += 1

        if bucket.consume(tokens):
            self._stats["allowed_requests"] += 1
            return True
        self._stats["rejected_requests"] += 1
        return False

    def check(self, key: str, tokens: float = 1.0) -> None:
        """Check and raise if exceeded."""
        if not self.allow(key, tokens):
            bucket = self._get_bucket(key)
            deficit = tokens - bucket.available_tokens
            retry_after = deficit / self.refill_rate
            raise RateLimitExceededError(key, retry_after)

    def get_remaining(self, key: str) -> int:
        """Return remaining requests for a key."""
        bucket = self._get_bucket(key)
        return int(bucket.available_tokens)

    def reset(self, key: str) -> None:
        """Reset the bucket for a key."""
        full_key = f"{self.key_prefix}{key}" if self.key_prefix else key
        with self._lock:
            self._buckets.pop(full_key, None)

    def limit(self, key_func: Callable | None = None) -> Callable:
        """Decorator to apply rate limiting."""

        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if key_func:
                    key = key_func(*args, **kwargs)
                elif args:
                    key = str(args[0])
                else:
                    key = "default"
                self.check(key)
                return func(*args, **kwargs)

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if key_func:
                    key = key_func(*args, **kwargs)
                elif args:
                    key = str(args[0])
                else:
                    key = "default"
                self.check(key)
                return await func(*args, **kwargs)

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return wrapper

        return decorator

    @property
    def stats(self) -> dict[str, int]:
        """Rate limiter statistics."""
        return self._stats.copy()

    def cleanup_expired(self, max_age: float = 3600) -> int:
        """Clean up expired buckets."""
        now = time.time()
        expired = []
        with self._lock:
            for key, bucket in self._buckets.items():
                if now - bucket.last_update > max_age:
                    expired.append(key)
            for key in expired:
                del self._buckets[key]
        return len(expired)


def create_scan_limiter() -> RateLimiter:
    """Rate limiter for web scanning (1 scan / 10 min per domain)."""
    return RateLimiter(rate=1, per=600, burst=2, key_prefix="scan:")
