"""SOIC v3.0 — Core data models.

Consolidated superset: domain-based (GateReport) + phase-based (PhaseGateReport).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class GateStatus(StrEnum):
    """Result status of a quality gate execution."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"
    NOT_EXECUTED = "NOT_EXECUTED"


@dataclass
class GateResult:
    """Result of a single gate execution.

    Supports both binary PASS/FAIL (code gates) and granular scoring 0.0-10.0
    (web gates with continuous metrics like Lighthouse).

    NOT_EXECUTED gates score 0.0 (not 5.0) to avoid inflating mu.
    """

    gate_id: str
    name: str
    status: GateStatus
    evidence: str
    duration_ms: int
    command: str
    dimension: str = ""  # D1-D9, used by phase-based gates
    score: float = 0.0  # 0.0-10.0, used by phase-based gates

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d: dict[str, Any] = {
            "gate_id": self.gate_id,
            "name": self.name,
            "status": self.status.value,
            "evidence": self.evidence,
            "duration_ms": self.duration_ms,
            "command": self.command,
        }
        if self.dimension:
            d["dimension"] = self.dimension
            d["score"] = round(self.score, 2)
        return d


@dataclass
class SOICScore:
    """Computed SOIC score from gate results."""

    mu: float
    pass_rate: float
    total_gates: int
    passed: int
    failed: int
    skipped: int
    failures: list[str]
    # Phase-based fields (dimension scoring)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    not_executed: int = 0
    coverage: float = 1.0  # gates actually executed / total

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        d: dict[str, Any] = {
            "mu": round(self.mu, 2),
            "pass_rate": round(self.pass_rate, 3),
            "total_gates": self.total_gates,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "failures": self.failures,
        }
        if self.dimension_scores:
            d["dimension_scores"] = {k: round(v, 2) for k, v in self.dimension_scores.items()}
            d["not_executed"] = self.not_executed
            d["coverage"] = round(self.coverage, 3)
        return d


@dataclass
class GateReport:
    """Full report from a domain-based gate engine run."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain: str = ""
    target_path: str = ""
    gates: list[GateResult] = field(default_factory=list)
    mu: float = 0.0
    pass_rate: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def compute_score(self) -> SOICScore:
        """Compute the SOIC score from gate results.

        mu = (PASS count / evaluated count) * 10
        Evaluated = total - SKIP count.
        """
        skipped = sum(1 for g in self.gates if g.status == GateStatus.SKIP)
        evaluated = len(self.gates) - skipped
        passed = sum(1 for g in self.gates if g.status == GateStatus.PASS)
        failed = sum(1 for g in self.gates if g.status in (GateStatus.FAIL, GateStatus.ERROR))
        fail_statuses = (GateStatus.FAIL, GateStatus.ERROR)
        failures = [g.gate_id for g in self.gates if g.status in fail_statuses]

        if evaluated > 0:
            self.pass_rate = passed / evaluated
            self.mu = self.pass_rate * 10
        else:
            self.pass_rate = 0.0
            self.mu = 0.0

        return SOICScore(
            mu=self.mu,
            pass_rate=self.pass_rate,
            total_gates=len(self.gates),
            passed=passed,
            failed=failed,
            skipped=skipped,
            failures=failures,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize full report to dictionary."""
        return {
            "run_id": self.run_id,
            "domain": self.domain,
            "target_path": self.target_path,
            "gates": [g.to_dict() for g in self.gates],
            "mu": self.mu,
            "pass_rate": self.pass_rate,
            "timestamp": self.timestamp,
        }


@dataclass
class PhaseGateReport:
    """Full report from a phase-based gate engine run (NEXOS web pipeline)."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    phase: str = ""
    client_slug: str = ""
    iteration: int = 1
    gates: list[GateResult] = field(default_factory=list)
    dimension_scores: dict[str, float] = field(default_factory=dict)
    mu: float = 0.0
    coverage: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def fail_count(self) -> int:
        """Number of FAIL + ERROR gates."""
        return sum(1 for g in self.gates if g.status in (GateStatus.FAIL, GateStatus.ERROR))

    def compute_score(self) -> SOICScore:
        """Aggregate gate scores by dimension, then compute mu via calculate_mu().

        NOT_EXECUTED gates count as 0.0 (not 5.0) -- they penalize the score.
        SKIP gates are excluded from scoring (neutral).
        Coverage = executed gates / total gates. If < 0.7 -> INCOMPLETE.
        """
        from .dimensions import DIMENSIONS, calculate_mu

        # Count statuses
        not_executed = sum(1 for g in self.gates if g.status == GateStatus.NOT_EXECUTED)
        skipped = sum(1 for g in self.gates if g.status == GateStatus.SKIP)
        actually_ran = len(self.gates) - skipped - not_executed

        # Coverage: proportion of gates that actually ran
        self.coverage = actually_ran / len(self.gates) if self.gates else 0.0

        # Group scores by dimension
        dim_scores: dict[str, list[float]] = {}
        for g in self.gates:
            if g.status == GateStatus.SKIP:
                continue
            if g.status == GateStatus.NOT_EXECUTED:
                dim_scores.setdefault(g.dimension, []).append(0.0)
            else:
                dim_scores.setdefault(g.dimension, []).append(g.score)

        # Average per dimension, 5.0 neutral for dimensions with zero gates
        self.dimension_scores = {}
        for dim_id in DIMENSIONS:
            scores = dim_scores.get(dim_id, [])
            self.dimension_scores[dim_id] = (
                sum(scores) / len(scores) if scores else 5.0
            )

        self.mu = calculate_mu(self.dimension_scores)

        # Stats
        passed = sum(1 for g in self.gates if g.status == GateStatus.PASS)
        failed = sum(1 for g in self.gates if g.status in (GateStatus.FAIL, GateStatus.ERROR))
        failures = [g.gate_id for g in self.gates if g.status in (GateStatus.FAIL, GateStatus.ERROR)]

        return SOICScore(
            mu=self.mu,
            dimension_scores=dict(self.dimension_scores),
            pass_rate=passed / actually_ran if actually_ran > 0 else 0.0,
            total_gates=len(self.gates),
            passed=passed,
            failed=failed,
            skipped=skipped,
            not_executed=not_executed,
            coverage=self.coverage,
            failures=failures,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize full report to dictionary."""
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "client_slug": self.client_slug,
            "iteration": self.iteration,
            "gates": [g.to_dict() for g in self.gates],
            "dimension_scores": {k: round(v, 2) for k, v in self.dimension_scores.items()},
            "mu": round(self.mu, 2),
            "coverage": round(self.coverage, 3),
            "timestamp": self.timestamp,
        }


@dataclass
class DeltaReport:
    """Delta between two scans (web or code)."""

    previous_score: float
    current_score: float
    delta: float
    improved_axes: list[str]
    regressed_axes: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "previous_score": self.previous_score,
            "current_score": self.current_score,
            "delta": self.delta,
            "improved_axes": self.improved_axes,
            "regressed_axes": self.regressed_axes,
        }
