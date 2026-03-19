"""Circuit Breaker Pattern Implementation.

Protects against cascading failures from external services.

States:
    CLOSED: Normal operation, requests pass through
    OPEN: Circuit tripped, requests fail fast
    HALF_OPEN: Testing if service recovered
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import wraps
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when the circuit is open."""

    def __init__(
        self, breaker_name: str, state: CircuitState, remaining_time: float = 0,
    ) -> None:
        self.breaker_name = breaker_name
        self.state = state
        self.remaining_time = remaining_time
        super().__init__(
            f"Circuit breaker '{breaker_name}' is {state.value}. "
            f"Retry in {remaining_time:.1f}s"
        )


@dataclass
class CircuitStats:
    """Circuit breaker statistics."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None


class CircuitBreaker:
    """Circuit Breaker for protecting against external service failures.

    Args:
        name: Circuit name (for logging).
        failure_threshold: Failures before opening (default: 5).
        recovery_timeout: Seconds before HALF_OPEN (default: 30).
        expected_exceptions: Exception types that trigger the breaker.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exceptions: tuple = (Exception,),
        on_state_change: Callable[[CircuitState, CircuitState], None] | None = None,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        self.on_state_change = on_state_change

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = Lock()
        self._stats = CircuitStats()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        with self._lock:
            if self._state == CircuitState.OPEN and self._should_attempt_reset():
                self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def stats(self) -> CircuitStats:
        """Circuit statistics."""
        return self._stats

    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return True
        return (time.time() - self._last_failure_time) >= self.recovery_timeout

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self._state
        if old_state != new_state:
            self._state = new_state
            self._stats.state_changes += 1
            logger.info("Circuit '%s': %s -> %s", self.name, old_state.value, new_state.value)
            if self.on_state_change:
                self.on_state_change(old_state, new_state)

    def _record_success(self) -> None:
        with self._lock:
            self._stats.total_calls += 1
            self._stats.successful_calls += 1
            self._stats.last_success_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._failure_count = 0
                self._transition_to(CircuitState.CLOSED)

    def _record_failure(self, exception: Exception) -> None:
        with self._lock:
            self._stats.total_calls += 1
            self._stats.failed_calls += 1
            self._stats.last_failure_time = time.time()
            self._failure_count += 1
            self._last_failure_time = time.time()

            should_open = (
                self._state == CircuitState.HALF_OPEN
                or (self._state == CircuitState.CLOSED
                    and self._failure_count >= self.failure_threshold)
            )
            if should_open:
                self._transition_to(CircuitState.OPEN)

    def _check_state(self) -> None:
        current_state = self.state
        if current_state == CircuitState.OPEN:
            self._stats.rejected_calls += 1
            remaining = self.recovery_timeout - (
                time.time() - (self._last_failure_time or 0)
            )
            raise CircuitBreakerError(self.name, current_state, max(0, remaining))

    def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute a function through the circuit breaker."""
        self._check_state()
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except self.expected_exceptions as e:
            self._record_failure(e)
            raise

    async def call_async(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Async version of call()."""
        self._check_state()
        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except self.expected_exceptions as e:
            self._record_failure(e)
            raise

    def __call__(self, func: Callable) -> Callable:
        """Decorator to protect a function."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.call(func, *args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self.call_async(func, *args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    def __enter__(self) -> CircuitBreaker:
        self._check_state()
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        if exc_type is None:
            self._record_success()
        elif (
            exc_val is not None
            and issubclass(exc_type, self.expected_exceptions)
            and isinstance(exc_val, Exception)
        ):
            self._record_failure(exc_val)

    def reset(self) -> None:
        """Manual reset of the circuit."""
        with self._lock:
            self._failure_count = 0
            self._last_failure_time = None
            self._transition_to(CircuitState.CLOSED)

    def get_status(self) -> dict:
        """Return status for health check."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "stats": {
                "total_calls": self._stats.total_calls,
                "successful_calls": self._stats.successful_calls,
                "failed_calls": self._stats.failed_calls,
                "rejected_calls": self._stats.rejected_calls,
            },
        }


def create_web_breaker() -> CircuitBreaker:
    """Circuit breaker for web scan operations."""
    return CircuitBreaker(
        name="web_scan",
        failure_threshold=3,
        recovery_timeout=60.0,
        expected_exceptions=(ConnectionError, TimeoutError, OSError),
    )
