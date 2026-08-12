"""Tests for soic.persistence."""

from pathlib import Path

from soic.models import GateReport, GateResult, GateStatus
from soic.persistence import RunStore


class TestRunStore:
    def _make_store(self, tmp_path: Path) -> RunStore:
        return RunStore(runs_dir=tmp_path / "runs")

    def test_save_and_get_history(self, tmp_path):
        store = self._make_store(tmp_path)
        report = GateReport(domain="CODE", target_path="/test")
        report.gates.append(GateResult(
            gate_id="C-01", name="ruff", status=GateStatus.PASS,
            evidence="Clean", duration_ms=10, command="ruff",
        ))
        report.compute_score()

        store.save_run(report)
        history = store.get_history(limit=10)
        assert len(history) == 1
        assert history[0]["domain"] == "CODE"

    def test_get_latest(self, tmp_path):
        store = self._make_store(tmp_path)

        # No runs yet
        assert store.get_latest() is None

        # Add a run
        report = GateReport(domain="CODE", target_path="/test")
        report.compute_score()
        store.save_run(report)

        latest = store.get_latest()
        assert latest is not None
        assert latest["domain"] == "CODE"

    def test_history_limit(self, tmp_path):
        store = self._make_store(tmp_path)
        for i in range(5):
            report = GateReport(domain="CODE", target_path=f"/test{i}")
            report.compute_score()
            store.save_run(report)

        assert len(store.get_history(limit=3)) == 3
        assert len(store.get_history(limit=10)) == 5


class TestWebPersistence:
    def _make_store(self, tmp_path: Path) -> RunStore:
        return RunStore(runs_dir=tmp_path / "runs")

    def test_save_and_get_web_history(self, tmp_path):
        store = self._make_store(tmp_path)
        url = "https://example.com"
        record = {
            "url": url,
            "osiris_score": 7.5,
            "grade": "Conforme",
            "axes": {"O": {"score": 8.0}, "S": {"score": 7.0}},
        }

        store.save_web_scan(url, record)
        history = store.get_web_history(url)
        assert len(history) == 1
        assert history[0]["osiris_score"] == 7.5

    def test_different_urls_different_files(self, tmp_path):
        store = self._make_store(tmp_path)
        store.save_web_scan("https://a.com", {"url": "https://a.com", "osiris_score": 5.0})
        store.save_web_scan("https://b.com", {"url": "https://b.com", "osiris_score": 8.0})

        assert len(store.get_web_history("https://a.com")) == 1
        assert len(store.get_web_history("https://b.com")) == 1

    def test_get_delta(self, tmp_path):
        store = self._make_store(tmp_path)
        url = "https://example.com"

        # Not enough history
        assert store.get_delta(url) is None

        # Two scans
        store.save_web_scan(url, {
            "osiris_score": 6.0, "axes": {"O": {"score": 5.0}, "S": {"score": 7.0}},
        })
        store.save_web_scan(url, {
            "osiris_score": 7.0, "axes": {"O": {"score": 7.0}, "S": {"score": 6.0}},
        })

        delta = store.get_delta(url)
        assert delta is not None
        assert delta.delta == 1.0
        assert "O" in delta.improved_axes
        assert "S" in delta.regressed_axes
