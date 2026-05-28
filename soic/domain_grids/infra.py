"""SOIC v3.0 — DOMAIN_INFRA: 5 quality gates for infrastructure files."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import register_domain
from ..models import GateResult, GateStatus

_GATE_TIMEOUT = 120


def _collect_files(path: str, patterns: list[str]) -> list[Path]:
    """Collect files matching glob patterns."""
    p = Path(path)
    if p.is_file():
        return [p]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(p.rglob(pattern))
    return sorted(set(files))


@dataclass
class YamllintGate:
    """I-01: YAML lint via yamllint."""

    gate_id: str = "I-01"
    name: str = "yamllint"
    tool: str = "yamllint"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        if not shutil.which(self.tool):
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence=f"Tool not found: {self.tool}",
                duration_ms=0,
                command="",
            )

        yaml_files = _collect_files(path, ["*.yml", "*.yaml"])
        if not yaml_files:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence="No YAML files found",
                duration_ms=0,
                command="",
            )

        cmd = [self.tool, "-f", "parsable"] + [str(f) for f in yaml_files]
        start = time.monotonic()
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                timeout=_GATE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.ERROR,
                evidence="Timeout",
                duration_ms=0,
                command=" ".join(cmd[:3]),
            )
        duration_ms = int((time.monotonic() - start) * 1000)

        errors = [line for line in proc.stdout.splitlines() if "[error]" in line]
        if errors:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=f"{len(errors)} YAML errors",
                duration_ms=duration_ms,
                command=" ".join(cmd[:3]),
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence=f"{len(yaml_files)} YAML files clean",
            duration_ms=duration_ms,
            command=" ".join(cmd[:3]),
        )


@dataclass
class DockerBuildCheckGate:
    """I-02: Dockerfile syntax check via docker build --check."""

    gate_id: str = "I-02"
    name: str = "docker-check"
    tool: str = "docker"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        dockerfiles = _collect_files(path, ["Dockerfile", "Dockerfile.*", "*.dockerfile"])
        if not dockerfiles:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence="No Dockerfiles found",
                duration_ms=0,
                command="",
            )

        if not shutil.which(self.tool):
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence=f"Tool not found: {self.tool}",
                duration_ms=0,
                command="",
            )

        start = time.monotonic()
        errors: list[str] = []
        for df in dockerfiles:
            cmd = [self.tool, "build", "--check", "-f", str(df), str(df.parent)]
            try:
                proc = subprocess.run(  # noqa: S603
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=_GATE_TIMEOUT,
                )
                if proc.returncode != 0:
                    errors.append(f"{df.name}: {proc.stderr[:100]}")
            except subprocess.TimeoutExpired:
                errors.append(f"{df.name}: timeout")

        duration_ms = int((time.monotonic() - start) * 1000)
        if errors:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=f"{len(errors)} Dockerfile error(s): {'; '.join(errors[:3])}",
                duration_ms=duration_ms,
                command="docker build --check",
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence=f"{len(dockerfiles)} Dockerfile(s) valid",
            duration_ms=duration_ms,
            command="docker build --check",
        )


@dataclass
class TrivyGate:
    """I-03: Filesystem vulnerability scan via trivy."""

    gate_id: str = "I-03"
    name: str = "trivy"
    tool: str = "trivy"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        if not shutil.which(self.tool):
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence=f"Tool not found: {self.tool}",
                duration_ms=0,
                command="",
            )

        cmd = [self.tool, "fs", "--severity", "CRITICAL,HIGH", "--format", "json", path]
        start = time.monotonic()
        try:
            proc = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                timeout=_GATE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.ERROR,
                evidence="Timeout",
                duration_ms=0,
                command=" ".join(cmd),
            )
        duration_ms = int((time.monotonic() - start) * 1000)

        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError:
            data = {}

        results = data.get("Results", [])
        vulns = sum(len(r.get("Vulnerabilities", [])) for r in results)
        if vulns > 0:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=f"{vulns} HIGH/CRITICAL vulnerabilities",
                duration_ms=duration_ms,
                command=" ".join(cmd),
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence="No HIGH/CRITICAL vulnerabilities",
            duration_ms=duration_ms,
            command=" ".join(cmd),
        )


@dataclass
class HadolintGate:
    """I-04: Dockerfile linting via hadolint."""

    gate_id: str = "I-04"
    name: str = "hadolint"
    tool: str = "hadolint"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        dockerfiles = _collect_files(path, ["Dockerfile", "Dockerfile.*", "*.dockerfile"])
        if not dockerfiles:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence="No Dockerfiles found",
                duration_ms=0,
                command="",
            )

        if not shutil.which(self.tool):
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence=f"Tool not found: {self.tool}",
                duration_ms=0,
                command="",
            )

        start = time.monotonic()
        total_issues = 0
        for df in dockerfiles:
            cmd = [self.tool, str(df)]
            try:
                proc = subprocess.run(  # noqa: S603
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=_GATE_TIMEOUT,
                )
                if proc.returncode != 0:
                    total_issues += len(proc.stdout.strip().splitlines())
            except subprocess.TimeoutExpired:
                total_issues += 1

        duration_ms = int((time.monotonic() - start) * 1000)
        if total_issues > 0:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=f"{total_issues} hadolint issue(s)",
                duration_ms=duration_ms,
                command=f"hadolint {dockerfiles[0].name}",
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence=f"{len(dockerfiles)} Dockerfile(s) clean",
            duration_ms=duration_ms,
            command=f"hadolint {dockerfiles[0].name}",
        )


@dataclass
class KubevalGate:
    """I-05: Kubernetes manifest validation via kubeval."""

    gate_id: str = "I-05"
    name: str = "kubeval"
    tool: str = "kubeval"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        k8s_files = _collect_files(path, ["*.yml", "*.yaml"])
        # Filter to likely K8s manifests
        k8s_manifests = []
        for f in k8s_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")[:500]
                if "apiVersion:" in content and "kind:" in content:
                    k8s_manifests.append(f)
            except OSError:
                continue

        if not k8s_manifests:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence="No Kubernetes manifests found",
                duration_ms=0,
                command="",
            )

        if not shutil.which(self.tool):
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence=f"Tool not found: {self.tool}",
                duration_ms=0,
                command="",
            )

        start = time.monotonic()
        errors: list[str] = []
        for manifest in k8s_manifests:
            cmd = [self.tool, str(manifest)]
            try:
                proc = subprocess.run(  # noqa: S603
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=_GATE_TIMEOUT,
                )
                if proc.returncode != 0:
                    errors.append(f"{manifest.name}")
            except subprocess.TimeoutExpired:
                errors.append(f"{manifest.name}: timeout")

        duration_ms = int((time.monotonic() - start) * 1000)
        if errors:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=f"{len(errors)} invalid manifest(s): {', '.join(errors[:5])}",
                duration_ms=duration_ms,
                command="kubeval",
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence=f"{len(k8s_manifests)} manifest(s) valid",
            duration_ms=duration_ms,
            command="kubeval",
        )


def _load_infra_gates() -> list:
    """Load all INFRA domain gates."""
    return [
        YamllintGate(),
        DockerBuildCheckGate(),
        TrivyGate(),
        HadolintGate(),
        KubevalGate(),
    ]


register_domain("INFRA", _load_infra_gates)
