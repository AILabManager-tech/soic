"""Tests for soic.feedback_router."""

from soic.feedback_router import FeedbackRouter, WebFeedbackRouter
from soic.models import GateReport, GateResult, GateStatus


class TestFeedbackRouter:
    def test_no_failures(self):
        router = FeedbackRouter()
        report = GateReport(domain="CODE", target_path="/test")
        report.gates.append(GateResult(
            gate_id="C-01", name="ruff", status=GateStatus.PASS,
            evidence="Clean", duration_ms=10, command="ruff",
        ))
        feedback = router.generate(report)
        assert "All gates passed" in feedback

    def test_with_failures(self):
        router = FeedbackRouter()
        report = GateReport(domain="CODE", target_path="/test")
        report.gates.append(GateResult(
            gate_id="C-01", name="ruff", status=GateStatus.FAIL,
            evidence="5 errors", duration_ms=10, command="ruff check /test",
        ))
        report.gates.append(GateResult(
            gate_id="C-02", name="bandit", status=GateStatus.PASS,
            evidence="Clean", duration_ms=10, command="bandit",
        ))
        feedback = router.generate(report)
        assert "C-01" in feedback
        assert "ruff" in feedback.lower()
        assert "C-02" not in feedback  # passed gate should not appear

    def test_path_substitution(self):
        router = FeedbackRouter()
        report = GateReport(domain="CODE", target_path="/my/project")
        report.gates.append(GateResult(
            gate_id="C-01", name="ruff", status=GateStatus.FAIL,
            evidence="3 errors", duration_ms=10, command="ruff",
        ))
        feedback = router.generate(report)
        assert "/my/project" in feedback


class TestWebFeedbackRouter:
    def test_no_recommendations_above_threshold(self):
        router = WebFeedbackRouter(threshold=7.0)
        axes = {
            "O": {"score": 8.0},
            "S": {"score": 9.0},
            "I": {"score": 10.0},
            "R": {"score": 7.5},
        }
        recs = router.generate(axes)
        assert len(recs) == 0

    def test_recommendations_below_threshold(self):
        router = WebFeedbackRouter(threshold=7.0)
        axes = {
            "O": {"score": 3.0},
            "S": {"score": 5.5},
            "I": {"score": 10.0},
            "R": {"score": 8.0},
        }
        recs = router.generate(axes)
        assert len(recs) == 2
        # S should have higher priority (weight=0.30) than O (weight=0.20)
        # despite O being lower, because priority = weight * potential
        # O: 0.20 * (7.0 - 3.0) = 0.80
        # S: 0.30 * (7.0 - 5.5) = 0.45
        assert recs[0]["axis"] == "O"  # Higher impact

    def test_with_delta(self):
        router = WebFeedbackRouter(threshold=7.0)
        axes = {"O": {"score": 4.0}}
        delta = {"O": -2.0}
        recs = router.generate(axes, delta=delta)
        assert len(recs) == 1
        assert "delta: -2.0" in recs[0]["recommendation"]
