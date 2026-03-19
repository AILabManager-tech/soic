"""Centralized Error Handler for SOIC v3.0."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any


class ErrorSeverity(Enum):
    """Error severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SOICError(Exception):
    """Base exception for SOIC errors."""

    def __init__(
        self,
        message: str,
        code: str = "SOIC_ERR",
        details: dict | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


class GateError(SOICError):
    """Gate execution specific errors."""

    def __init__(self, message: str, gate_id: str | None = None, **kwargs: Any) -> None:
        super().__init__(message, code="GATE_ERR", **kwargs)
        self.details["gate_id"] = gate_id


class ScanError(SOICError):
    """Web scan specific errors."""

    def __init__(self, message: str, url: str | None = None, **kwargs: Any) -> None:
        super().__init__(message, code="SCAN_ERR", **kwargs)
        self.details["url"] = url


class ErrorHandler:
    """Centralized error handling with history tracking."""

    _instance: ErrorHandler | None = None
    _initialized: bool = False

    def __new__(cls) -> ErrorHandler:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self.logger = logging.getLogger("soic_v3.errors")
        self.error_history: list[dict] = []
        self.max_history = 1000
        self._initialized = True

    def handle(
        self,
        error: Exception,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: dict | None = None,
        reraise: bool = False,
    ) -> dict[str, Any]:
        """Handle an error with logging and tracking."""
        context = context or {}

        if isinstance(error, SOICError):
            report = error.to_dict()
        else:
            report = {
                "error_type": type(error).__name__,
                "code": "UNKNOWN_ERR",
                "message": str(error),
                "details": {},
                "timestamp": datetime.now().isoformat(),
            }

        report["severity"] = severity.value
        report["context"] = context
        report["traceback"] = traceback.format_exc()

        log_method = getattr(self.logger, severity.value)
        log_method("[%s] %s", report["code"], report["message"])

        self.error_history.append(report)
        if len(self.error_history) > self.max_history:
            self.error_history.pop(0)

        if reraise:
            raise error

        return report

    def get_statistics(self) -> dict[str, Any]:
        """Get error statistics."""
        if not self.error_history:
            return {"total": 0, "by_severity": {}, "by_code": {}}

        by_severity: dict[str, int] = {}
        by_code: dict[str, int] = {}
        for err in self.error_history:
            sev = err.get("severity", "unknown")
            code = err.get("code", "unknown")
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_code[code] = by_code.get(code, 0) + 1

        return {
            "total": len(self.error_history),
            "by_severity": by_severity,
            "by_code": by_code,
        }

    def clear_history(self) -> None:
        self.error_history.clear()


def handle_errors(
    default_return: Any = None,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    reraise: bool = False,
) -> Callable:
    """Decorator for automatic error handling."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handler = ErrorHandler()
                handler.handle(
                    e,
                    severity=severity,
                    context={"function": func.__name__},
                    reraise=reraise,
                )
                return default_return

        return wrapper

    return decorator
