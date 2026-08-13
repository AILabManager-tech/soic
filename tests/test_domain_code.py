"""Tests for soic.domain_grids.code."""

import subprocess
from unittest.mock import MagicMock, patch

from soic.domain_grids.code import (
    BanditGate,
    GitleaksGate,
    MypyGate,
    PytestGate,
    RadonGate,
    RuffGate,
)
from soic.models import GateStatus


class TestRuffGate:
    @patch("shutil.which", return_value=None)
    def test_skip_when_not_installed(self, _mock):
        gate = RuffGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.SKIP

    @patch("shutil.which", return_value="/usr/bin/ruff")
    @patch("soic.domain_grids.code.CodeGate._run_cmd")
    def test_pass_clean(self, mock_run, _mock_which):
        proc = MagicMock()
        proc.stdout = "All checks passed!"
        proc.stderr = ""
        mock_run.return_value = (proc, 42)

        gate = RuffGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.PASS
        assert result.evidence == "Clean"

    @patch("shutil.which", return_value="/usr/bin/ruff")
    @patch("soic.domain_grids.code.CodeGate._run_cmd")
    def test_fail_errors(self, mock_run, _mock_which):
        proc = MagicMock()
        proc.stdout = "Found 5 errors"
        proc.stderr = ""
        mock_run.return_value = (proc, 100)

        gate = RuffGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.FAIL
        assert "5 errors" in result.evidence


class TestBanditGate:
    @patch("shutil.which", return_value="/usr/bin/bandit")
    @patch("soic.domain_grids.code.CodeGate._run_cmd")
    def test_pass_no_issues(self, mock_run, _mock_which):
        proc = MagicMock()
        proc.stdout = '{"results": []}'
        proc.stderr = ""
        mock_run.return_value = (proc, 50)

        gate = BanditGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.PASS

    @patch("shutil.which", return_value="/usr/bin/bandit")
    @patch("soic.domain_grids.code.CodeGate._run_cmd")
    def test_fail_high_severity(self, mock_run, _mock_which):
        proc = MagicMock()
        proc.stdout = '{"results": [{"issue_severity": "HIGH"}]}'
        proc.stderr = ""
        mock_run.return_value = (proc, 50)

        gate = BanditGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.FAIL
        assert "HIGH" in result.evidence


class TestPytestGate:
    @patch("shutil.which", return_value="/usr/bin/pytest")
    @patch("soic.domain_grids.code.CodeGate._run_cmd")
    def test_pass(self, mock_run, _mock_which):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = "========== 10 passed in 1.5s =========="
        proc.stderr = ""
        mock_run.return_value = (proc, 1500)

        gate = PytestGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.PASS
        assert "10 passed" in result.evidence


class TestRadonGate:
    @patch("shutil.which", return_value="/usr/bin/radon")
    @patch("soic.domain_grids.code.CodeGate._run_cmd")
    def test_pass_low_complexity(self, mock_run, _mock_which):
        proc = MagicMock()
        proc.stdout = "Average complexity: A (3.5)"
        proc.stderr = ""
        mock_run.return_value = (proc, 80)

        gate = RadonGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.PASS
        assert "3.50" in result.evidence

    @patch("shutil.which", return_value="/usr/bin/radon")
    @patch("soic.domain_grids.code.CodeGate._run_cmd")
    def test_fail_high_complexity(self, mock_run, _mock_which):
        proc = MagicMock()
        proc.stdout = "Average complexity: C (20.5)"
        proc.stderr = ""
        mock_run.return_value = (proc, 80)

        gate = RadonGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.FAIL


class TestMypyGate:
    @patch("shutil.which", return_value="/usr/bin/mypy")
    @patch("soic.domain_grids.code.CodeGate._run_cmd")
    def test_pass_clean(self, mock_run, _mock_which):
        proc = MagicMock()
        proc.stdout = "Success: no issues found"
        proc.stderr = ""
        mock_run.return_value = (proc, 200)

        gate = MypyGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.PASS


class TestGitleaksGate:
    @patch("shutil.which", return_value="/usr/bin/gitleaks")
    @patch("soic.domain_grids.code.CodeGate._run_cmd")
    def test_pass_no_secrets(self, mock_run, _mock_which):
        proc = MagicMock()
        proc.stdout = "[]"
        proc.stderr = ""
        mock_run.return_value = (proc, 60)

        gate = GitleaksGate()
        result = gate.run("/tmp/test")
        assert result.status == GateStatus.PASS
        assert "No secrets" in result.evidence


class TestMissingExecutable:
    """Un binaire absent doit dégrader la gate, pas faire tomber l'évaluation."""

    def test_pytest_gate_uses_the_running_interpreter(self):
        # Le code appelait "python" en dur. Ubuntu 24.04 ne fournit que
        # python3 : hors venv activé, `soic evaluate --domain CODE` mourait
        # sur un FileNotFoundError non attrapé, avant même de noter quoi que
        # ce soit. sys.executable existe toujours, par construction.
        import sys

        gate = PytestGate()
        with patch.object(gate, "_tool_available", return_value=True), \
             patch.object(gate, "_run_cmd") as run_cmd:
            run_cmd.return_value = (
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
                1,
            )
            gate.run("/tmp")

        assert run_cmd.call_args[0][0][0] == sys.executable

    def test_missing_binary_yields_error_not_crash(self):
        gate = RuffGate()
        with patch.object(gate, "_tool_available", return_value=True), \
             patch.object(gate, "_run_cmd", side_effect=FileNotFoundError(2, "x", "absent-bin")):
            result = gate.run("/tmp")

        assert result.status == GateStatus.ERROR
        assert "absent-bin" in result.evidence

    def test_pytest_availability_follows_the_interpreter_not_the_path(self):
        # _tool_available cherchait un binaire pytest sur le PATH pendant que
        # run() lançait `sys.executable -m pytest`. Un /usr/bin/pytest système
        # faisait répondre "disponible" à un interpréteur qui n'a pas le
        # module : la gate rendait FAIL au lieu de SKIP, et un FAIL pèse sur mu.
        gate = PytestGate()
        with patch("importlib.util.find_spec", return_value=None), \
             patch("shutil.which", return_value="/usr/bin/pytest"):
            result = gate.run("/tmp")

        assert result.status == GateStatus.SKIP
