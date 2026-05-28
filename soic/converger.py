"""SOIC v3.0 — Converger: iteration decision engine.

Consolidated: supports both domain-based (code) and phase-based (web/NEXOS) modes.

Phase-based rules (NEXOS):
- D4 (Security) and D8 (Legal) are non-negotiable: FAIL blocks ACCEPT.
- Coverage < 0.7 -> ABORT (insufficient tooling data).
- Plateau detected -> ENRICHED_RETRY once (with PlateauDiagnosis injected in
  feedback), then ABORT_PLATEAU if the next iteration still plateaus.
- max_iter default = 4 for a real chance at convergence.

Plateau recovery (P8.2, post-codex challenge 019e2baf):
  Before P8.2 a plateau immediately aborted the loop, leaving NEXOS silent
  on the failure mode (collectif-nova mu=8.05, vertex-pmo mu=7.91 both
  ABORT_PLATEAU with no diagnostic). Codex flagged that "switching models is
  a weak hypothesis until you know why plateau happens" — so the recovery
  here is informational, not architectural:

    1. On first plateau, return ENRICHED_RETRY and surface a `PlateauDiagnosis`
       describing which dimensions stagnated and which assertions still fail.
    2. The iterator forwards this diagnosis to the rerun callback (typically
       via FeedbackRouter.generate_with_plateau_context), giving the next LLM
       call concrete failing-gate context instead of a fresh prompt.
    3. If the second pass still plateaus, ABORT_PLATEAU fires for real.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import GateReport, GateStatus, PhaseGateReport

# Phase thresholds for ACCEPT decision (NEXOS)
_PHASE_THRESHOLDS: dict[str, float] = {
    "ph0-discovery": 7.0,
    "ph1-strategy": 8.0,
    "ph2-design": 8.0,
    "ph3-content": 8.0,
    "ph4-build": 7.0,
    "ph5-qa": 8.5,
}

# Non-negotiable dimensions: FAIL blocks ACCEPT regardless of mu
_BLOCKING_DIMENSIONS = {"D4", "D8"}

# Minimum coverage required to accept
_MIN_COVERAGE = 0.7


class Decision(StrEnum):
    """Convergence decision after an evaluation."""

    ACCEPT = "ACCEPT"
    ITERATE = "ITERATE"
    ENRICHED_RETRY = "ENRICHED_RETRY"
    ABORT_PLATEAU = "ABORT_PLATEAU"
    ABORT_MAX_ITER = "ABORT_MAX_ITER"
    ABORT_LOW_COVERAGE = "ABORT_LOW_COVERAGE"


@dataclass(frozen=True)
class FailingAssertion:
    """One failed gate captured at plateau-detection time.

    The triple `(gate_id, dimension, score)` is enough for the LLM to act on:
    `gate_id` indexes the corrective template in FeedbackRouter, `dimension`
    routes priority, `score` shows how close (or far) the gate was from passing.
    """

    gate_id: str
    name: str
    dimension: str
    score: float
    evidence: str


@dataclass(frozen=True)
class PlateauDiagnosis:
    """Snapshot of *why* the Converger detected a plateau.

    Returned by `Converger.diagnose_plateau` whenever the loop is about to
    suggest `ENRICHED_RETRY` (or has already given up via `ABORT_PLATEAU`).
    Consumed by the iterator + FeedbackRouter to inject concrete failure
    context into the next phase prompt — replaces the previous silent abort
    behaviour (P8.2).
    """

    iteration: int
    mu_trajectory: tuple[float, ...]
    fail_trajectory: tuple[int, ...]
    failing_dimensions: tuple[str, ...]
    failing_assertions: tuple[FailingAssertion, ...]
    phase: str | None = None

    def is_empty(self) -> bool:
        """True if no failing assertions were found (defensive — should not
        normally happen since a plateau implies unresolved failures, but the
        converger may be invoked on a coverage-stripped report)."""
        return not self.failing_assertions

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "phase": self.phase,
            "mu_trajectory": list(self.mu_trajectory),
            "fail_trajectory": list(self.fail_trajectory),
            "failing_dimensions": list(self.failing_dimensions),
            "failing_assertions": [
                {
                    "gate_id": a.gate_id,
                    "name": a.name,
                    "dimension": a.dimension,
                    "score": a.score,
                    "evidence": a.evidence,
                }
                for a in self.failing_assertions
            ],
        }


class Converger:
    """Decides whether to accept, iterate, or abort based on gate results.

    Supports both domain-based (phase=None) and phase-based modes.
    """

    def __init__(self, max_iter: int = 3, phase: str | None = None) -> None:
        self.phase = phase
        self.max_iter = max_iter
        self.mu_history: list[float] = []
        self.fail_history: list[int] = []
        self.threshold = _PHASE_THRESHOLDS.get(phase, 8.0) if phase else None
        # Last gate report (kept for plateau diagnosis after `decide`).
        self._last_report: GateReport | PhaseGateReport | None = None
        # ENRICHED_RETRY is offered once per Converger lifecycle. After it
        # fires, a subsequent plateau yields ABORT_PLATEAU. Reset by `reset()`.
        self._enriched_retry_used: bool = False
        # Snapshot of the most recent diagnosis (None until a plateau is detected).
        self._last_diagnosis: PlateauDiagnosis | None = None

    def decide(self, report: GateReport | PhaseGateReport, iteration: int) -> Decision:
        """Evaluate the report and return a decision.

        Args:
            report: The latest gate evaluation report (GateReport or PhaseGateReport).
            iteration: Current iteration number (1-based).

        Returns:
            Decision enum value.
        """
        self.mu_history.append(report.mu)
        self._last_report = report

        # Track fail count
        if isinstance(report, PhaseGateReport):
            self.fail_history.append(report.fail_count)
        else:
            fail_count = sum(
                1 for g in report.gates if g.status in (GateStatus.FAIL, GateStatus.ERROR)
            )
            self.fail_history.append(fail_count)

        # Phase-based coverage check
        if isinstance(report, PhaseGateReport) and report.coverage < _MIN_COVERAGE:
            return Decision.ABORT_LOW_COVERAGE

        # Phase-based: check blocking dimensions + threshold
        if self.phase and isinstance(report, PhaseGateReport):
            blocking_fail = any(
                g.status in (GateStatus.FAIL, GateStatus.ERROR)
                for g in report.gates
                if g.dimension in _BLOCKING_DIMENSIONS
            )
            if report.mu >= self.threshold and not blocking_fail:
                return Decision.ACCEPT
        else:
            # Domain-based: all gates PASS -> accept
            all_pass = all(g.status in (GateStatus.PASS, GateStatus.SKIP) for g in report.gates)
            if all_pass:
                return Decision.ACCEPT

        # Max iterations reached
        if iteration >= self.max_iter:
            return Decision.ABORT_MAX_ITER

        # Plateau detection — first hit yields ENRICHED_RETRY (informational
        # second pass), second hit yields ABORT_PLATEAU (give up for real).
        if self._is_plateau():
            self._last_diagnosis = self._build_diagnosis(report, iteration)
            if not self._enriched_retry_used:
                self._enriched_retry_used = True
                return Decision.ENRICHED_RETRY
            return Decision.ABORT_PLATEAU

        return Decision.ITERATE

    def _build_diagnosis(
        self,
        report: GateReport | PhaseGateReport,
        iteration: int,
    ) -> PlateauDiagnosis:
        """Snapshot failing gates + score trajectory at plateau-detection time."""
        failed_gates = [g for g in report.gates if g.status in (GateStatus.FAIL, GateStatus.ERROR)]
        assertions = tuple(
            FailingAssertion(
                gate_id=g.gate_id,
                name=g.name,
                dimension=g.dimension,
                score=g.score,
                evidence=g.evidence,
            )
            for g in failed_gates
        )
        # Preserve insertion order of dimensions (dict.fromkeys = ordered set).
        dimensions = tuple(dict.fromkeys(g.dimension for g in failed_gates))
        return PlateauDiagnosis(
            iteration=iteration,
            mu_trajectory=tuple(self.mu_history),
            fail_trajectory=tuple(self.fail_history),
            failing_dimensions=dimensions,
            failing_assertions=assertions,
            phase=self.phase,
        )

    def diagnose_plateau(self) -> PlateauDiagnosis | None:
        """Return the most recent plateau diagnosis, if any.

        `None` while the loop is still progressing (no plateau detected yet).
        Once `decide()` returns `ENRICHED_RETRY` or `ABORT_PLATEAU`, this
        returns the snapshot captured at that point.
        """
        return self._last_diagnosis

    def _is_plateau(self) -> bool:
        """Detect plateau: 2 consecutive non-positive mu deltas.

        Even with stagnant mu, fewer failures = qualitative progress (not a plateau).
        """
        if len(self.mu_history) < 3:
            return False
        delta_prev = self.mu_history[-2] - self.mu_history[-3]
        delta_curr = self.mu_history[-1] - self.mu_history[-2]
        two_non_positive = delta_prev <= 0 and delta_curr <= 0
        # Even with stagnant mu, fewer failures = qualitative progress
        if len(self.fail_history) >= 2:
            fewer_failures = self.fail_history[-1] < self.fail_history[-2]
            return two_non_positive and not fewer_failures
        return two_non_positive

    def reset(self) -> None:
        """Reset history for a fresh run."""
        self.mu_history.clear()
        self.fail_history.clear()
        self._enriched_retry_used = False
        self._last_diagnosis = None
        self._last_report = None

    def get_summary(self, decision: Decision, iteration: int) -> str:
        """Return a human-readable summary of the decision."""
        mu_str = f"mu={self.mu_history[-1]:.2f}" if self.mu_history else "mu=N/A"

        if self.phase:
            summaries = {
                Decision.ACCEPT: f"ACCEPT -- {mu_str} >= {self.threshold} (seuil {self.phase})",
                Decision.ITERATE: f"ITERATE -- Iteration {iteration}/{self.max_iter} ({mu_str} < {self.threshold})",
                Decision.ENRICHED_RETRY: (
                    f"ENRICHED_RETRY -- Plateau detecte ({mu_str}) -- "
                    f"1 derniere tentative avec diagnostic injecte"
                ),
                Decision.ABORT_PLATEAU: f"ABORT -- Score plateau detected ({mu_str})",
                Decision.ABORT_MAX_ITER: f"ABORT -- Max iterations reached ({mu_str})",
                Decision.ABORT_LOW_COVERAGE: f"ABORT -- Couverture insuffisante (coverage < {_MIN_COVERAGE}) -- executer le preflight d'abord",
            }
        else:
            summaries = {
                Decision.ACCEPT: f"ACCEPT -- All gates passed ({mu_str})",
                Decision.ITERATE: f"ITERATE -- Iteration {iteration}/{self.max_iter} ({mu_str})",
                Decision.ENRICHED_RETRY: (
                    f"ENRICHED_RETRY -- Plateau detected ({mu_str}) -- "
                    f"retrying once with injected diagnosis"
                ),
                Decision.ABORT_PLATEAU: f"ABORT -- Score plateau detected ({mu_str})",
                Decision.ABORT_MAX_ITER: f"ABORT -- Max iterations reached ({mu_str})",
                Decision.ABORT_LOW_COVERAGE: f"ABORT -- Low coverage ({mu_str})",
            }
        return summaries[decision]


class WebConverger:
    """Convergence analysis for web scan history.

    Analyzes the trend of a site across multiple scans:
    - improving: scores are going up
    - stable: scores are flat
    - degrading: scores are going down
    """

    def __init__(self, plateau_threshold: float = 0.3) -> None:
        self.plateau_threshold = plateau_threshold

    def analyze_trend(self, scores: list[float]) -> str:
        """Determine the trend from a list of chronological scores.

        Returns:
            One of 'improving', 'stable', 'degrading', or 'insufficient_data'.
        """
        if len(scores) < 2:
            return "insufficient_data"

        deltas = [scores[i] - scores[i - 1] for i in range(1, len(scores))]
        avg_delta = sum(deltas) / len(deltas)

        if avg_delta > self.plateau_threshold:
            return "improving"
        if avg_delta < -self.plateau_threshold:
            return "degrading"
        return "stable"

    def detect_plateau(self, scores: list[float]) -> bool:
        """Return True if the last 3+ scores show no meaningful change."""
        if len(scores) < 3:
            return False
        recent = scores[-3:]
        spread = max(recent) - min(recent)
        return spread <= self.plateau_threshold

    def detect_regression(self, scores: list[float]) -> bool:
        """Return True if the latest score is lower than the previous."""
        if len(scores) < 2:
            return False
        return scores[-1] < scores[-2] - self.plateau_threshold
