"""SOIC v3.0 — Persistence: JSON Lines storage for run history.

Consolidated: supports both runs_dir-based (code) and client_dir-based (NEXOS).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import DeltaReport, GateReport, PhaseGateReport

_DEFAULT_RUNS_DIR = "soic_runs"
_RUNS_FILE = "runs.jsonl"
_CLIENT_RUNS_FILE = "soic-runs.jsonl"


class RunStore:
    """Append-only JSON Lines store for SOIC run reports.

    Two modes:
    - runs_dir mode: RunStore() or RunStore("soic_runs") -- code-domain
    - client_dir mode: RunStore("/path/to/client") -- NEXOS phase-based
    """

    def __init__(self, runs_dir: str | Path = _DEFAULT_RUNS_DIR) -> None:
        self.runs_dir = Path(runs_dir)
        # Detect mode: if the directory looks like a client dir (has site/ or soic-runs.jsonl)
        client_runs = self.runs_dir / _CLIENT_RUNS_FILE
        if client_runs.exists() or (self.runs_dir / "site").exists():
            self.runs_file = client_runs
        else:
            self.runs_file = self.runs_dir / _RUNS_FILE

    def _ensure_dir(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def save_run(self, report: GateReport | PhaseGateReport) -> Path:
        """Append a run report to the JSONL file."""
        self._ensure_dir()
        with self.runs_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
        return self.runs_file

    def get_history(
        self, limit: int = 20, phase: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the last N runs, optionally filtered by phase."""
        if not self.runs_file.exists():
            return []
        lines = self.runs_file.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                if phase and entry.get("phase") != phase:
                    continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue
        return entries[-limit:]

    def get_latest(self, phase: str | None = None) -> dict[str, Any] | None:
        """Return the most recent run, or None."""
        history = self.get_history(limit=1, phase=phase)
        return history[0] if history else None

    # --- Web scan persistence (OSIRIS) ---

    @staticmethod
    def _url_key(url: str) -> str:
        """Hash a URL into a short key for per-target storage."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _target_file(self, url: str) -> Path:
        """Return the JSONL file for a specific target URL."""
        return self.runs_dir / f"web_{self._url_key(url)}.jsonl"

    def save_web_scan(self, url: str, record: dict[str, Any]) -> Path:
        """Persist a web scan record keyed by URL."""
        self._ensure_dir()
        target_file = self._target_file(url)
        with target_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return target_file

    def get_web_history(self, url: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return the last N web scans for a URL."""
        target_file = self._target_file(url)
        if not target_file.exists():
            return []
        lines = target_file.read_text(encoding="utf-8").strip().splitlines()
        entries = [json.loads(line) for line in lines if line.strip()]
        return entries[-limit:]

    def get_web_latest(self, url: str) -> dict[str, Any] | None:
        """Return the most recent web scan for a URL."""
        history = self.get_web_history(url, limit=1)
        return history[0] if history else None

    def get_delta(self, url: str) -> DeltaReport | None:
        """Compute the delta between the two most recent web scans."""
        history = self.get_web_history(url, limit=2)
        if len(history) < 2:
            return None

        prev, curr = history[-2], history[-1]
        prev_score = prev.get("osiris_score", 0.0)
        curr_score = curr.get("osiris_score", 0.0)

        prev_axes = prev.get("axes", {})
        curr_axes = curr.get("axes", {})

        improved = []
        regressed = []
        for axis in ("O", "S", "I", "R"):
            ps = prev_axes.get(axis, {}).get("score", 0.0)
            cs = curr_axes.get(axis, {}).get("score", 0.0)
            if cs > ps:
                improved.append(axis)
            elif cs < ps:
                regressed.append(axis)

        return DeltaReport(
            previous_score=prev_score,
            current_score=curr_score,
            delta=round(curr_score - prev_score, 2),
            improved_axes=improved,
            regressed_axes=regressed,
        )
