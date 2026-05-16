"""SOIC v3.0 — Iterators: orchestrate the evaluate-decide-feedback loop.

Consolidated: SOICIterator (domain-based) + PhaseIterator (NEXOS phase-based).

PhaseIterator features:
- rerun_phase callback (orchestrator re-executes Claude CLI with feedback)
- Per-client persistence via RunStore
- Global timeout (default 15 min) to prevent runaway loops
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .converger import Converger, Decision, PlateauDiagnosis
from .feedback_router import FeedbackRouter
from .gate_engine import GateEngine
from .models import GateReport, PhaseGateReport
from .persistence import RunStore


@dataclass
class IterationResult:
    """Result of a single iteration within the loop."""

    iteration: int
    report: GateReport | PhaseGateReport
    decision: Decision
    feedback: str
    summary: str
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        d = {
            "iteration": self.iteration,
            "report": self.report.to_dict(),
            "decision": self.decision.value,
            "summary": self.summary,
        }
        if self.duration_s > 0:
            d["duration_s"] = round(self.duration_s, 1)
            d["feedback_length"] = len(self.feedback)
        else:
            d["feedback"] = self.feedback
        return d


@dataclass
class LoopResult:
    """Full result of an iteration loop."""

    iterations: list[IterationResult] = field(default_factory=list)
    final_decision: Decision = Decision.ITERATE
    final_mu: float = 0.0
    abort_reason: str = ""

    @property
    def total_iterations(self) -> int:
        return len(self.iterations)

    @property
    def converged(self) -> bool:
        return self.final_decision == Decision.ACCEPT

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "total_iterations": self.total_iterations,
            "converged": self.converged,
            "final_decision": self.final_decision.value,
            "final_mu": round(self.final_mu, 2),
            "abort_reason": self.abort_reason,
            "iterations": [it.to_dict() for it in self.iterations],
        }


# Type aliases
IterationCallback = Callable[[int, IterationResult], None]
RerunCallback = Callable[[str, str, int], bool]  # (phase, feedback, iteration) -> success
EnrichedRetryHook = Callable[[PlateauDiagnosis], None]
"""Hook invoked when `Decision.ENRICHED_RETRY` fires (P8.3).

The host (NEXOS orchestrator) receives the `PlateauDiagnosis` snapshot
captured by the Converger and can take dimension-scoped corrective action
(e.g., trigger `auto_fix(dimensions=diagnosis.failing_dimensions)`) BEFORE
the phase is re-prompted to the LLM. SOIC has no knowledge of what the
host does in this hook — that decoupling keeps SOIC pure.

Called exactly once per plateau: after `diagnose_plateau()` returns the
snapshot and before `rerun_phase` re-executes the phase prompt. If the
hook raises, the exception propagates and the loop stops with the
exception unhandled — let the host decide on error semantics.
"""


class SOICIterator:
    """Orchestrates the full SOIC iteration loop (domain-based).

    Loop: evaluate -> decide -> feedback -> (repeat or stop)
    """

    def __init__(
        self,
        domain: str,
        target_path: str,
        test_path: str | None = None,
        max_iter: int = 3,
    ) -> None:
        self.domain = domain
        self.target_path = target_path
        self.test_path = test_path
        self.max_iter = max_iter
        self.converger = Converger(max_iter=max_iter)
        self.feedback_router = FeedbackRouter()
        self.store = RunStore()

    def run(self, on_iteration: IterationCallback | None = None) -> LoopResult:
        """Execute the full iteration loop.

        Args:
            on_iteration: Optional callback called after each iteration
                with (iteration_number, IterationResult).

        Returns:
            LoopResult with all iteration details.
        """
        loop = LoopResult()

        for i in range(1, self.max_iter + 1):
            engine = GateEngine(
                domain=self.domain,
                target_path=self.target_path,
                test_path=self.test_path,
            )
            report = engine.run_all_gates()
            self.store.save_run(report)

            decision = self.converger.decide(report, iteration=i)
            summary = self.converger.get_summary(decision, iteration=i)

            if decision == Decision.ACCEPT:
                feedback = "All gates passed. No corrective action needed."
            elif decision == Decision.ENRICHED_RETRY:
                diagnosis = self.converger.diagnose_plateau()
                if diagnosis is None:
                    feedback = self.feedback_router.generate(report)
                else:
                    feedback = self.feedback_router.generate_with_plateau_context(report, diagnosis)
            else:
                feedback = self.feedback_router.generate(report)

            result = IterationResult(
                iteration=i,
                report=report,
                decision=decision,
                feedback=feedback,
                summary=summary,
            )
            loop.iterations.append(result)

            if on_iteration is not None:
                on_iteration(i, result)

            if decision in (Decision.ACCEPT, Decision.ABORT_PLATEAU, Decision.ABORT_MAX_ITER):
                loop.final_decision = decision
                loop.final_mu = report.mu
                break

        if not loop.iterations:
            loop.final_decision = Decision.ABORT_MAX_ITER
        elif loop.final_decision == Decision.ITERATE:
            loop.final_decision = Decision.ABORT_MAX_ITER
            loop.final_mu = loop.iterations[-1].report.mu

        return loop


class PhaseIterator:
    """Orchestrates the full SOIC iteration loop for a NEXOS phase.

    Loop: evaluate -> decide -> feedback -> rerun -> (repeat or stop)
    """

    def __init__(
        self,
        phase: str,
        client_dir: str,
        max_iter: int = 4,
        store: RunStore | None = None,
        site_dir: str | None = None,
        timeout_minutes: int = 15,
        on_enriched_retry: EnrichedRetryHook | None = None,
    ) -> None:
        self.phase = phase
        self.client_dir = client_dir
        self.site_dir = site_dir
        self.max_iter = max_iter
        self.timeout_seconds = timeout_minutes * 60
        self.converger = Converger(phase=phase, max_iter=max_iter)
        self.feedback_router = FeedbackRouter()
        self.store = store or RunStore(client_dir)
        # P8.3 — optional hook invoked on Decision.ENRICHED_RETRY, after the
        # plateau diagnosis has been captured and before the phase is re-run.
        # SOIC ignores what the host does in the hook (typically: trigger a
        # dimension-scoped auto-fix in NEXOS).
        self.on_enriched_retry = on_enriched_retry

    def run(
        self,
        rerun_phase: RerunCallback | None = None,
        on_iteration: IterationCallback | None = None,
    ) -> LoopResult:
        """Execute the full iteration loop.

        Args:
            rerun_phase: Callback to re-execute the phase with feedback.
                Signature: (phase, feedback_markdown, iteration) -> success.
                If None, the loop only evaluates once (no re-runs).
            on_iteration: Optional callback after each iteration for CLI output.

        Returns:
            LoopResult with all iteration details.
        """
        loop = LoopResult()
        loop_start = time.monotonic()

        for i in range(1, self.max_iter + 1):
            iter_start = time.monotonic()

            # Check global timeout
            elapsed = time.monotonic() - loop_start
            if elapsed >= self.timeout_seconds:
                loop.final_decision = Decision.ABORT_MAX_ITER
                loop.final_mu = loop.iterations[-1].report.mu if loop.iterations else 0.0
                loop.abort_reason = f"Timeout global atteint ({self.timeout_seconds // 60}min)"
                break

            # 1. Evaluate
            engine = GateEngine(
                phase=self.phase,
                client_dir=self.client_dir,
                site_dir=self.site_dir,
            )
            report = engine.run_all_gates(iteration=i)
            self.store.save_run(report)

            # 2. Decide
            decision = self.converger.decide(report, iteration=i)
            summary = self.converger.get_summary(decision, iteration=i)

            # 3. Feedback (enrich with plateau diagnosis on ENRICHED_RETRY — P8.2)
            #    + invoke on_enriched_retry hook for dimension-scoped recovery (P8.3)
            if decision == Decision.ACCEPT:
                feedback = "All quality criteria met. No corrective action needed."
            elif decision == Decision.ENRICHED_RETRY:
                diagnosis = self.converger.diagnose_plateau()
                if diagnosis is None:
                    feedback = self.feedback_router.generate(report)
                else:
                    feedback = self.feedback_router.generate_with_plateau_context(report, diagnosis)
                    # P8.3 — let the host take dimension-scoped corrective action
                    # before the rerun (e.g., NEXOS auto-fix on failing_dimensions).
                    # Called AFTER diagnose_plateau and BEFORE rerun_phase so the
                    # filesystem state seen by the rerun reflects the corrections.
                    if self.on_enriched_retry is not None:
                        self.on_enriched_retry(diagnosis)
            else:
                feedback = self.feedback_router.generate(report)

            iter_duration = time.monotonic() - iter_start
            result = IterationResult(
                iteration=i,
                report=report,
                decision=decision,
                feedback=feedback,
                summary=summary,
                duration_s=iter_duration,
            )
            loop.iterations.append(result)

            if on_iteration is not None:
                on_iteration(i, result)

            # Stop conditions
            stop_decisions = (
                Decision.ACCEPT,
                Decision.ABORT_PLATEAU,
                Decision.ABORT_MAX_ITER,
                Decision.ABORT_LOW_COVERAGE,
            )
            if decision in stop_decisions:
                loop.final_decision = decision
                loop.final_mu = report.mu
                if decision == Decision.ABORT_LOW_COVERAGE:
                    loop.abort_reason = "Couverture insuffisante -- executer le preflight d'abord"
                break

            # 4. Re-run phase with feedback
            if rerun_phase is not None:
                success = rerun_phase(self.phase, feedback, i)
                if not success:
                    loop.final_decision = Decision.ABORT_MAX_ITER
                    loop.final_mu = report.mu
                    loop.abort_reason = "rerun_phase callback returned False"
                    break
            else:
                # No rerun callback -- just evaluate once
                loop.final_decision = decision
                loop.final_mu = report.mu
                break

        # Ensure final state is set
        if not loop.iterations:
            loop.final_decision = Decision.ABORT_MAX_ITER
        elif loop.final_decision == Decision.ITERATE:
            loop.final_decision = Decision.ABORT_MAX_ITER
            loop.final_mu = loop.iterations[-1].report.mu

        return loop
