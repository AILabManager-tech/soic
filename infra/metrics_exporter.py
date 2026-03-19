"""Metrics Exporter for SOIC v3.0.

Lightweight metrics tracking without external dependencies.
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any


class MetricsExporter:
    """Simple metrics tracking for SOIC operations."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self.gauges: dict[str, float] = {}
        self.histograms: dict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, value: int = 1) -> None:
        """Increment a counter."""
        self.counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value."""
        self.gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        """Record a histogram observation."""
        self.histograms[name].append(value)

    @contextmanager
    def track_request(self, operation: str):
        """Context manager for tracking operation duration."""
        start = time.time()
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            duration = time.time() - start
            self.observe(f"{operation}_duration", duration)
            self.inc(f"{operation}_{status}")

    def get_metrics_dict(self) -> dict[str, Any]:
        """Return all metrics as a dictionary."""
        result: dict[str, Any] = {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
        }

        hist_summary = {}
        for name, values in self.histograms.items():
            if values:
                hist_summary[name] = {
                    "count": len(values),
                    "total": sum(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }
        result["histograms"] = hist_summary
        return result

    def reset(self) -> None:
        """Reset all metrics."""
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()


# Singleton
_exporter: MetricsExporter | None = None


def get_metrics_exporter() -> MetricsExporter:
    """Get the singleton MetricsExporter."""
    global _exporter
    if _exporter is None:
        _exporter = MetricsExporter()
    return _exporter
