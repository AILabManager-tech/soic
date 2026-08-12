"""Tests for soic.gate_engine."""

from unittest.mock import MagicMock, patch

from soic.gate_engine import GateEngine
from soic.models import GateReport, GateResult, GateStatus


class TestGateEngine:
    @patch("soic.gate_engine.get_domain_gates")
    def test_run_all_gates(self, mock_get_gates):
        """GateEngine should run all gates and return a report."""
        mock_gate1 = MagicMock()
        mock_gate1.gate_id = "C-01"
        mock_gate1.run.return_value = GateResult(
            gate_id="C-01", name="ruff", status=GateStatus.PASS,
            evidence="Clean", duration_ms=50, command="ruff check .",
        )
        mock_gate2 = MagicMock()
        mock_gate2.gate_id = "C-02"
        mock_gate2.run.return_value = GateResult(
            gate_id="C-02", name="bandit", status=GateStatus.FAIL,
            evidence="1 HIGH issue", duration_ms=30, command="bandit -r .",
        )
        mock_get_gates.return_value = [mock_gate1, mock_gate2]

        engine = GateEngine(domain="CODE", target_path="/tmp/test")
        report = engine.run_all_gates()

        assert isinstance(report, GateReport)
        assert len(report.gates) == 2
        assert report.gates[0].status == GateStatus.PASS
        assert report.gates[1].status == GateStatus.FAIL
        assert report.mu == 5.0  # 1 pass / 2 evaluated

    @patch("soic.gate_engine.get_domain_gates")
    def test_run_gate_by_id(self, mock_get_gates):
        """GateEngine should run a single gate by ID."""
        mock_gate = MagicMock()
        mock_gate.gate_id = "C-01"
        mock_gate.run.return_value = GateResult(
            gate_id="C-01", name="ruff", status=GateStatus.PASS,
            evidence="Clean", duration_ms=50, command="ruff check .",
        )
        mock_get_gates.return_value = [mock_gate]

        engine = GateEngine(domain="CODE", target_path="/tmp/test")
        result = engine.run_gate("C-01")

        assert result.gate_id == "C-01"
        assert result.status == GateStatus.PASS

    @patch("soic.gate_engine.get_domain_gates")
    def test_run_gate_not_found(self, mock_get_gates):
        """GateEngine should raise ValueError for unknown gate ID."""
        mock_get_gates.return_value = []
        engine = GateEngine(domain="CODE", target_path="/tmp/test")

        try:
            engine.run_gate("NONEXISTENT")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "NONEXISTENT" in str(e)
