"""SOIC v3.0 — OSIRIS Adapter: bridge between OSIRIS results and SOIC persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .models import DeltaReport
from .persistence import RunStore


def save_osiris_scan(
    url: str,
    results: dict[str, Any],
    osiris_score: float,
    grade: str,
    store: RunStore,
) -> dict[str, Any]:
    """Persist an OSIRIS web scan result.

    Args:
        url: The scanned URL.
        results: Dict of axis_key -> AxisResult-like objects (need .score, .details, .tool_used).
        osiris_score: Composite OSIRIS score.
        grade: OSIRIS grade string.
        store: RunStore instance.

    Returns:
        The persisted record dict.
    """
    axes: dict[str, dict[str, Any]] = {}
    for axis_key, axis_result in results.items():
        axes[axis_key] = {
            "score": axis_result.score,
            "tool_used": axis_result.tool_used,
            "details": axis_result.details,
        }

    record = {
        "url": url,
        "osiris_score": osiris_score,
        "grade": grade,
        "axes": axes,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    store.save_web_scan(url, record)
    return record


def get_osiris_history(
    url: str,
    store: RunStore,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Retrieve scan history for a URL.

    Args:
        url: The target URL.
        store: RunStore instance.
        limit: Max number of records.

    Returns:
        List of scan records, most recent last.
    """
    return store.get_web_history(url, limit=limit)


def compute_osiris_delta(
    url: str,
    store: RunStore,
) -> DeltaReport | None:
    """Compute the delta between the two most recent scans.

    Args:
        url: The target URL.
        store: RunStore instance.

    Returns:
        DeltaReport or None if insufficient history.
    """
    return store.get_delta(url)
