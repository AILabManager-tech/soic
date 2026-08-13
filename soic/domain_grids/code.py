"""SOIC v3.0 — DOMAIN_CODE: 6 quality gates for Python codebases."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Protocol

from ..models import GateResult, GateStatus
from . import register_domain

_GATE_TIMEOUT = 120


class Gate(Protocol):
    """Protocol for a quality gate."""

    gate_id: str
    name: str

    def run(self, path: str, test_path: str | None = None) -> GateResult: ...


@dataclass
class CodeGate:
    """Base for CODE domain gates."""

    gate_id: str
    name: str
    tool: str

    def _tool_available(self) -> bool:
        return shutil.which(self.tool) is not None

    def _skip_result(self) -> GateResult:
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.SKIP,
            evidence=f"Tool not found: {self.tool}",
            duration_ms=0,
            command="",
        )

    def _run_cmd(self, cmd: list[str]) -> tuple[subprocess.CompletedProcess[str], int]:
        """Run a command and return (result, duration_ms)."""
        start = time.monotonic()
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=_GATE_TIMEOUT,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return result, duration_ms

    def _error_result(self, cmd: list[str], error: str, duration_ms: int) -> GateResult:
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.ERROR,
            evidence=error,
            duration_ms=duration_ms,
            command=" ".join(cmd),
        )

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        raise NotImplementedError


@dataclass
class RuffGate(CodeGate):
    """C-01: Lint check via ruff."""

    gate_id: str = "C-01"
    name: str = "ruff"
    tool: str = "ruff"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        if not self._tool_available():
            return self._skip_result()

        cmd = [self.tool, "check", path, "--statistics"]
        try:
            proc, duration_ms = self._run_cmd(cmd)
        except subprocess.TimeoutExpired:
            return self._error_result(cmd, "Timeout", 0)
        except FileNotFoundError as exc:
            return self._error_result(cmd, f"Executable not found: {exc.filename}", 0)

        output = proc.stdout + proc.stderr
        match = re.search(r"Found (\d+) error", output)
        error_count = int(match.group(1)) if match else 0
        status = GateStatus.FAIL if error_count > 0 else GateStatus.PASS
        evidence = f"{error_count} errors found" if error_count > 0 else "Clean"

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=status,
            evidence=evidence,
            duration_ms=duration_ms,
            command=" ".join(cmd),
        )


@dataclass
class BanditGate(CodeGate):
    """C-02: Security scan via bandit."""

    gate_id: str = "C-02"
    name: str = "bandit"
    tool: str = "bandit"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        if not self._tool_available():
            return self._skip_result()

        cmd = [self.tool, "-r", path, "-f", "json", "-q"]
        try:
            proc, duration_ms = self._run_cmd(cmd)
        except subprocess.TimeoutExpired:
            return self._error_result(cmd, "Timeout", 0)
        except FileNotFoundError as exc:
            return self._error_result(cmd, f"Executable not found: {exc.filename}", 0)

        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError:
            return self._error_result(cmd, f"JSON parse error: {proc.stdout[:200]}", duration_ms)

        results = data.get("results", [])
        high_critical = sum(1 for r in results if r.get("issue_severity") in ("HIGH", "CRITICAL"))
        status = GateStatus.FAIL if high_critical > 0 else GateStatus.PASS
        evidence = (
            f"{high_critical} HIGH/CRITICAL issues"
            if high_critical > 0
            else "No HIGH/CRITICAL issues"
        )

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=status,
            evidence=evidence,
            duration_ms=duration_ms,
            command=" ".join(cmd),
        )


@dataclass
class PytestGate(CodeGate):
    """C-03: Test execution via pytest."""

    gate_id: str = "C-03"
    name: str = "pytest"
    tool: str = "pytest"

    def _tool_available(self) -> bool:
        # Les autres gates lancent un binaire : shutil.which suffit. Celle-ci
        # lance `sys.executable -m pytest`, donc ce qui compte est que le
        # module soit importable par CET interpréteur. Chercher un binaire sur
        # le PATH répondait oui alors que l'exécution échouait, et la gate
        # rendait FAIL au lieu de SKIP — un FAIL pèse sur mu, pas un SKIP.
        return importlib.util.find_spec("pytest") is not None

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        if not self._tool_available():
            return self._skip_result()

        target = test_path or path
        cmd = [
            # sys.executable, pas "python" : Ubuntu 24.04 ne fournit que
            # python3, et hors venv activé le binaire "python" n'existe pas.
            sys.executable,
            "-m",
            "pytest",
            target,
            "--tb=line",
            "-q",
            "-o",
            "addopts=",
            "--continue-on-collection-errors",
        ]
        try:
            proc, duration_ms = self._run_cmd(cmd)
        except subprocess.TimeoutExpired:
            return self._error_result(cmd, "Timeout", 0)
        except FileNotFoundError as exc:
            return self._error_result(cmd, f"Executable not found: {exc.filename}", 0)

        output = proc.stdout + proc.stderr
        status = GateStatus.PASS if proc.returncode == 0 else GateStatus.FAIL
        # Extract summary line (e.g. "399 passed, 17 failed")
        summary_match = re.search(r"=+ (.+) =+", output)
        evidence = summary_match.group(1) if summary_match else output[-300:].strip()

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=status,
            evidence=evidence,
            duration_ms=duration_ms,
            command=" ".join(cmd),
        )


@dataclass
class RadonGate(CodeGate):
    """C-04: Cyclomatic complexity via radon."""

    gate_id: str = "C-04"
    name: str = "radon"
    tool: str = "radon"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        if not self._tool_available():
            return self._skip_result()

        cmd = [self.tool, "cc", path, "-a"]
        try:
            proc, duration_ms = self._run_cmd(cmd)
        except subprocess.TimeoutExpired:
            return self._error_result(cmd, "Timeout", 0)
        except FileNotFoundError as exc:
            return self._error_result(cmd, f"Executable not found: {exc.filename}", 0)

        output = proc.stdout
        match = re.search(r"Average complexity:.*?\((\d+\.?\d*)\)", output)
        if match:
            avg = float(match.group(1))
            status = GateStatus.FAIL if avg > 15 else GateStatus.PASS
            evidence = f"Average complexity: {avg:.2f}"
        else:
            status = GateStatus.PASS
            evidence = "No measurable complexity"

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=status,
            evidence=evidence,
            duration_ms=duration_ms,
            command=" ".join(cmd),
        )


@dataclass
class MypyGate(CodeGate):
    """C-05: Type checking via mypy."""

    gate_id: str = "C-05"
    name: str = "mypy"
    tool: str = "mypy"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        if not self._tool_available():
            return self._skip_result()

        cmd = [self.tool, path, "--ignore-missing-imports"]
        try:
            proc, duration_ms = self._run_cmd(cmd)
        except subprocess.TimeoutExpired:
            return self._error_result(cmd, "Timeout", 0)
        except FileNotFoundError as exc:
            return self._error_result(cmd, f"Executable not found: {exc.filename}", 0)

        output = proc.stdout + proc.stderr
        match = re.search(r"Found (\d+) error", output)
        error_count = int(match.group(1)) if match else 0
        status = GateStatus.FAIL if error_count > 0 else GateStatus.PASS
        evidence = f"{error_count} type errors" if error_count > 0 else "Clean"

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=status,
            evidence=evidence,
            duration_ms=duration_ms,
            command=" ".join(cmd),
        )


@dataclass
class GitleaksGate(CodeGate):
    """C-06: Secret detection via gitleaks."""

    gate_id: str = "C-06"
    name: str = "gitleaks"
    tool: str = "gitleaks"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        if not self._tool_available():
            return self._skip_result()

        cmd = [
            self.tool,
            "detect",
            "--source",
            path,
            "--no-git",
            "--report-format",
            "json",
            "--report-path",
            "/dev/stdout",
        ]
        try:
            proc, duration_ms = self._run_cmd(cmd)
        except subprocess.TimeoutExpired:
            return self._error_result(cmd, "Timeout", 0)
        except FileNotFoundError as exc:
            return self._error_result(cmd, f"Executable not found: {exc.filename}", 0)

        # gitleaks exit code: 0 = no leaks, 1 = leaks found
        try:
            findings = json.loads(proc.stdout) if proc.stdout.strip() else []
        except json.JSONDecodeError:
            findings = []

        count = len(findings) if isinstance(findings, list) else 0
        status = GateStatus.FAIL if count > 0 else GateStatus.PASS
        evidence = f"{count} secrets detected" if count > 0 else "No secrets detected"

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=status,
            evidence=evidence,
            duration_ms=duration_ms,
            command=" ".join(cmd),
        )


def _load_code_gates() -> list[Gate]:
    """Load all CODE domain gates."""
    return [
        RuffGate(),
        BanditGate(),
        PytestGate(),
        RadonGate(),
        MypyGate(),
        GitleaksGate(),
    ]


# Auto-register on import
register_domain("CODE", _load_code_gates)
