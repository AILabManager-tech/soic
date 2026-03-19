"""SOIC v3.0 — WebGate base class (Gate Protocol).

Base class for all web-specific quality gates (NEXOS pipeline).
Adapted from AINOVA's CodeGate for web-specific quality gates.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .models import GateResult, GateStatus

_GATE_TIMEOUT = 120


@dataclass
class WebGate:
    """Base class for all NEXOS web quality gates."""

    gate_id: str
    name: str
    dimension: str  # D1-D9
    tool: str  # CLI tool name or "filesystem"/"grep"

    def _tool_available(self) -> bool:
        """Check if the CLI tool exists on PATH."""
        if self.tool in ("filesystem", "grep"):
            return True
        return shutil.which(self.tool) is not None

    def _skip_result(self, reason: str = "") -> GateResult:
        """Return a SKIP result with neutral 5.0 score.

        Use for legitimate skips (e.g. "vitest not in dependencies").
        """
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=GateStatus.SKIP,
            score=5.0,
            evidence=reason or f"Tool not found: {self.tool}",
            duration_ms=0,
            command="",
        )

    def _not_executed_result(self, reason: str = "") -> GateResult:
        """Return a NOT_EXECUTED result with 0.0 score.

        Use when tooling data is missing (e.g. lighthouse.json absent).
        This penalizes the score instead of inflating it with a fake 5.0.
        """
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=GateStatus.NOT_EXECUTED,
            score=0.0,
            evidence=reason or f"Tooling data missing for {self.gate_id}",
            duration_ms=0,
            command="",
        )

    def _run_cmd(
        self, cmd: list[str], cwd: str | None = None, timeout: int = _GATE_TIMEOUT,
    ) -> tuple[subprocess.CompletedProcess[str], int]:
        """Execute a CLI command with timing. Returns (result, duration_ms)."""
        start = time.monotonic()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return result, duration_ms

    def _error_result(self, cmd: str, error: str, duration_ms: int) -> GateResult:
        """Return an ERROR result."""
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=GateStatus.ERROR,
            score=0.0,
            evidence=error[:500],
            duration_ms=duration_ms,
            command=cmd,
        )

    def _read_tooling_json(self, tooling_dir: Path, filename: str) -> dict | list | None:
        """Read a pre-existing JSON from the tooling/ directory."""
        path = tooling_dir / filename
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        """Execute the gate. Must be overridden by subclasses."""
        raise NotImplementedError(f"{self.gate_id} must implement run()")
