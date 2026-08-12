"""Tests for soic.converger."""

from soic.converger import Converger, Decision, WebConverger
from soic.models import GateReport, GateResult, GateStatus


def _make_report(pass_count: int, fail_count: int, mu: float = 0.0) -> GateReport:
    """Create a report with given pass/fail counts."""
    report = GateReport(domain="CODE", target_path="/test")
    for i in range(pass_count):
        report.gates.append(GateResult(
            gate_id=f"C-{i:02d}", name=f"pass{i}", status=GateStatus.PASS,
            evidence="ok", duration_ms=10, command="cmd",
        ))
    for i in range(fail_count):
        report.gates.append(GateResult(
            gate_id=f"F-{i:02d}", name=f"fail{i}", status=GateStatus.FAIL,
            evidence="fail", duration_ms=10, command="cmd",
        ))
    report.compute_score()
    return report


class TestConverger:
    def test_accept_all_pass(self):
        c = Converger(max_iter=3)
        report = _make_report(pass_count=6, fail_count=0)
        decision = c.decide(report, iteration=1)
        assert decision == Decision.ACCEPT

    def test_iterate_with_failures(self):
        c = Converger(max_iter=3)
        report = _make_report(pass_count=4, fail_count=2)
        decision = c.decide(report, iteration=1)
        assert decision == Decision.ITERATE

    def test_abort_max_iter(self):
        c = Converger(max_iter=3)
        report = _make_report(pass_count=4, fail_count=2)
        c.decide(report, iteration=1)
        c.decide(report, iteration=2)
        decision = c.decide(report, iteration=3)
        assert decision == Decision.ABORT_MAX_ITER

    def test_abort_plateau(self):
        # Depuis P8.2 (550631c), le premier plateau rend ENRICHED_RETRY —
        # une passe informative avec PlateauDiagnosis — et ce n'est qu'au
        # plateau suivant que ABORT_PLATEAU tombe pour de bon.
        c = Converger(max_iter=5)
        report = _make_report(pass_count=4, fail_count=2)
        c.decide(report, iteration=1)
        c.decide(report, iteration=2)
        assert c.decide(report, iteration=3) == Decision.ENRICHED_RETRY
        decision = c.decide(report, iteration=4)
        assert decision == Decision.ABORT_PLATEAU

    def test_reset(self):
        c = Converger()
        report = _make_report(pass_count=4, fail_count=2)
        c.decide(report, iteration=1)
        assert len(c.mu_history) == 1
        c.reset()
        assert len(c.mu_history) == 0

    def test_get_summary(self):
        c = Converger()
        report = _make_report(pass_count=6, fail_count=0)
        decision = c.decide(report, iteration=1)
        summary = c.get_summary(decision, iteration=1)
        assert "ACCEPT" in summary


class TestWebConverger:
    def test_improving(self):
        wc = WebConverger()
        assert wc.analyze_trend([5.0, 6.0, 7.0, 8.0]) == "improving"

    def test_degrading(self):
        wc = WebConverger()
        assert wc.analyze_trend([8.0, 7.0, 6.0, 5.0]) == "degrading"

    def test_stable(self):
        wc = WebConverger()
        assert wc.analyze_trend([7.0, 7.1, 7.0, 7.2]) == "stable"

    def test_insufficient_data(self):
        wc = WebConverger()
        assert wc.analyze_trend([7.0]) == "insufficient_data"

    def test_detect_plateau(self):
        wc = WebConverger()
        assert wc.detect_plateau([7.0, 7.1, 7.0]) is True
        assert wc.detect_plateau([5.0, 7.0, 9.0]) is False

    def test_detect_regression(self):
        wc = WebConverger()
        assert wc.detect_regression([7.0, 5.0]) is True
        assert wc.detect_regression([7.0, 7.5]) is False
