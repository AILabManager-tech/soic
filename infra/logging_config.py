"""SOIC v3.0 Logging Configuration.

Provides structured logging with color and JSON formatters.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from typing import Any


class ColoredFormatter(logging.Formatter):
    """Formatter with ANSI colors for terminal output."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname_colored = f"{color}{self.BOLD}{record.levelname:8}{self.RESET}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """Formatter that outputs JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(
    name: str = "soic_v3",
    level: int = logging.INFO,
    console: bool = True,
) -> logging.Logger:
    """Setup and return a configured logger.

    Args:
        name: Logger name.
        level: Logging level.
        console: Enable console output.

    Returns:
        Configured logger instance.
    """
    log = logging.getLogger(name)
    log.setLevel(level)

    if log.handlers:
        return log

    if console:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        fmt = ColoredFormatter(
            "%(asctime)s | %(levelname_colored)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(fmt)
        log.addHandler(handler)

    return log


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger."""
    log = logging.getLogger(name)
    if not log.handlers:
        return setup_logging(name)
    return log
