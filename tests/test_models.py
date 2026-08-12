"""Tests for soic.models."""

from soic.models import DeltaReport, GateReport, GateResult, GateStatus, SOICScore


class TestGateStatus:
    def test_values(self):
        assert GateStatus.PASS.value == "PASS"
        assert GateStatus.FAIL.value == "FAIL"
        assert GateStatus.SKIP.value == "SKIP"
        assert GateStatus.ERROR.value == "ERROR"


class TestGateResult:
    def test_to_dict(self):
        r = GateResult(
            gate_id="C-01", name="ruff", status=GateStatus.PASS,
            evidence="Clean", duration_ms=100, command="ruff check .",
        )
        d = r.to_dict()
        assert d["gate_id"] == "C-01"
        assert d["status"] == "PASS"
        assert d["evidence"] == "Clean"
        assert d["duration_ms"] == 100


class TestGateReport:
    def test_compute_score_all_pass(self):
        report = GateReport(domain="CODE", target_path=".")
        for i in range(6):
            report.gates.append(GateResult(
                gate_id=f"C-0{i+1}", name=f"gate{i+1}", status=GateStatus.PASS,
                evidence="ok", duration_ms=10, command="cmd",
            ))
        score = report.compute_score()
        assert score.mu == 10.0
        assert score.pass_rate == 1.0
        assert score.passed == 6
        assert score.failed == 0
        assert score.failures == []

    def test_compute_score_mixed(self):
        report = GateReport(domain="CODE", target_path=".")
        report.gates.append(GateResult(
            gate_id="C-01", name="ruff", status=GateStatus.PASS,
            evidence="ok", duration_ms=10, command="cmd",
        ))
        report.gates.append(GateResult(
            gate_id="C-02", name="bandit", status=GateStatus.FAIL,
            evidence="1 issue", duration_ms=20, command="cmd",
        ))
        report.gates.append(GateResult(
            gate_id="C-03", name="pytest", status=GateStatus.SKIP,
            evidence="skipped", duration_ms=0, command="",
        ))
        score = report.compute_score()
        # 1 pass out of 2 evaluated (1 skip excluded)
        assert score.mu == 5.0
        assert score.passed == 1
        assert score.failed == 1
        assert score.skipped == 1
        assert "C-02" in score.failures

    def test_compute_score_empty(self):
        report = GateReport(domain="CODE", target_path=".")
        score = report.compute_score()
        assert score.mu == 0.0
        assert score.total_gates == 0

    def test_to_dict(self):
        report = GateReport(domain="CODE", target_path="/tmp/test")
        d = report.to_dict()
        assert d["domain"] == "CODE"
        assert d["target_path"] == "/tmp/test"
        assert isinstance(d["gates"], list)
        assert "run_id" in d
        assert "timestamp" in d


class TestSOICScore:
    def test_to_dict(self):
        score = SOICScore(
            mu=8.33, pass_rate=0.833, total_gates=6,
            passed=5, failed=1, skipped=0, failures=["C-02"],
        )
        d = score.to_dict()
        assert d["mu"] == 8.33
        assert d["failures"] == ["C-02"]


class TestDeltaReport:
    def test_to_dict(self):
        delta = DeltaReport(
            previous_score=6.5, current_score=7.2, delta=0.7,
            improved_axes=["O", "S"], regressed_axes=["I"],
        )
        d = delta.to_dict()
        assert d["delta"] == 0.7
        assert "O" in d["improved_axes"]
        assert "I" in d["regressed_axes"]
