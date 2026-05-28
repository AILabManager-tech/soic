"""SOIC v3.0 — Gate Engine: orchestrates quality gate execution.

Consolidated: supports both domain-based and phase-based gate execution.
"""

from __future__ import annotations

from pathlib import Path

from .domain_grids import get_domain_gates, get_phase_gates
from .models import GateReport, GateResult, PhaseGateReport, SOICScore


class GateEngine:
    """Orchestrates gate execution for a given domain or NEXOS phase.

    Domain mode: GateEngine(domain="CODE", target_path="/path/to/src")
    Phase mode:  GateEngine(phase="ph5-qa", client_dir="/path/to/client")
    """

    def __init__(
        self,
        domain: str | None = None,
        target_path: str | None = None,
        test_path: str | None = None,
        phase: str | None = None,
        client_dir: str | None = None,
        site_dir: str | None = None,
    ) -> None:
        if phase:
            # Phase-based mode (NEXOS web pipeline)
            self.mode = "phase"
            self.phase = phase
            self.client_dir = client_dir or ""
            self.site_dir = site_dir or str(Path(self.client_dir) / "site")
            self.gates = get_phase_gates(phase)
            # Also store for backward compat
            self.domain = ""
            self.target_path = ""
            self.test_path = None
        elif domain:
            # Domain-based mode (code quality)
            self.mode = "domain"
            self.domain = domain.upper()
            self.target_path = target_path or ""
            self.test_path = test_path
            self.gates = get_domain_gates(self.domain)
            # Also store for phase compat
            self.phase = ""
            self.client_dir = ""
            self.site_dir = ""
        else:
            raise ValueError("Either 'domain' or 'phase' must be provided")

    def run_gate(self, gate_id: str) -> GateResult:
        """Execute a single gate by ID."""
        for gate in self.gates:
            if gate.gate_id == gate_id:
                if self.mode == "phase":
                    return gate.run(self.client_dir, self.site_dir)
                return gate.run(self.target_path, self.test_path)
        label = self.phase if self.mode == "phase" else self.domain
        raise ValueError(f"Gate {gate_id!r} not found in {label}")

    def run_all_gates(self, iteration: int = 1) -> GateReport | PhaseGateReport:
        """Execute all gates and return a report.

        Returns GateReport for domain mode, PhaseGateReport for phase mode.
        """
        if self.mode == "phase":
            client_slug = Path(self.client_dir).name
            report = PhaseGateReport(
                phase=self.phase,
                client_slug=client_slug,
                iteration=iteration,
            )
            for gate in self.gates:
                result = gate.run(self.client_dir, self.site_dir)
                report.gates.append(result)
            report.compute_score()
            return report
        else:
            report = GateReport(domain=self.domain, target_path=self.target_path)
            for gate in self.gates:
                result = gate.run(self.target_path, self.test_path)
                report.gates.append(result)
            report.compute_score()
            return report

    def get_score(self, report: GateReport | PhaseGateReport) -> SOICScore:
        """Compute score from an existing report."""
        return report.compute_score()
