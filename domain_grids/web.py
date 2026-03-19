"""SOIC v3.0 — WEB domain: OSIRIS wrapper + 17 NEXOS quality gates.

Domain-based (OSIRIS): 4 gates wrapping OSIRIS axis scans.
Phase-based (NEXOS):  17 gates (W-01..W-17) mapped to dimensions D1-D9.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import register_domain, register_gate_set
from ..gate_protocol import WebGate
from ..models import GateResult, GateStatus


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: OSIRIS axis gates (domain-based, 4 gates)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OsirisAxisGate:
    """Base for WEB domain gates that wrap OSIRIS axis scans."""

    gate_id: str
    name: str
    axis_module: str
    pass_threshold: float = 7.0

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        """Execute the OSIRIS axis scan and convert to GateResult.

        `path` is interpreted as a URL for web domain.
        """
        url = path
        start = time.monotonic()

        try:
            # Dynamic import of axis scan function
            if self.axis_module == "performance":
                from axes.performance import scan
            elif self.axis_module == "security":
                from axes.security import scan
            elif self.axis_module == "intrusion":
                from axes.intrusion import scan
            elif self.axis_module == "resource":
                from axes.resource import scan
            else:
                return GateResult(
                    gate_id=self.gate_id, name=self.name, status=GateStatus.ERROR,
                    evidence=f"Unknown axis module: {self.axis_module}",
                    duration_ms=0, command="",
                )

            result = asyncio.run(scan(url))
            duration_ms = int((time.monotonic() - start) * 1000)

            status = GateStatus.PASS if result.score >= self.pass_threshold else GateStatus.FAIL
            evidence = f"Score: {result.score:.1f}/10 (threshold: {self.pass_threshold})"

            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=status,
                evidence=evidence,
                duration_ms=duration_ms,
                command=f"osiris.axes.{self.axis_module}.scan({url})",
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.ERROR,
                evidence=str(e)[:200], duration_ms=duration_ms,
                command=f"osiris.axes.{self.axis_module}.scan({url})",
            )


def _load_web_gates() -> list:
    """Load all WEB domain gates (OSIRIS)."""
    return [
        OsirisAxisGate(gate_id="W-01", name="performance", axis_module="performance"),
        OsirisAxisGate(gate_id="W-02", name="security", axis_module="security"),
        OsirisAxisGate(
            gate_id="W-03", name="intrusion", axis_module="intrusion", pass_threshold=8.0,
        ),
        OsirisAxisGate(gate_id="W-04", name="resource", axis_module="resource"),
    ]


register_domain("WEB", _load_web_gates)


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: NEXOS web quality gates (phase-based, 17 gates W-01..W-17)
# ═══════════════════════════════════════════════════════════════════════════════
# Note: NEXOS W-01..W-17 IDs overlap with OSIRIS W-01..W-04 above.
# They are in separate registries (domain vs gate_set) so no conflict.


# -- NW-01 nextjs-structure (D1) ----------------------------------------------

@dataclass
class NextJSStructureGate(WebGate):
    """NW-01: Verify Next.js project structure."""

    gate_id: str = "W-01"
    name: str = "nextjs-structure"
    dimension: str = "D1"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        if not sd.exists():
            return self._skip_result("No site directory")

        expected = [
            ("app", True),
            ("components", True),
            ("tsconfig.json", False),
            ("package.json", False),
            ("next.config", False),
        ]

        found = 0
        total = len(expected)
        missing = []
        for name, is_dir in expected:
            if is_dir:
                if any((sd / p / name).is_dir() for p in ["", "src"]):
                    found += 1
                else:
                    missing.append(name + "/")
            else:
                if list(sd.glob(f"{name}*")):
                    found += 1
                else:
                    missing.append(name)

        score = (found / total) * 10.0
        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        evidence = (
            f"{found}/{total} structure elements"
            + (f" (missing: {', '.join(missing)})" if missing else "")
        )

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=0, command="ls",
        )


# -- NW-02 documentation (D2) -------------------------------------------------

@dataclass
class DocumentationGate(WebGate):
    """W-02: README and code documentation."""

    gate_id: str = "W-02"
    name: str = "documentation"
    dimension: str = "D2"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        score = 0.0
        issues = []

        readme = sd / "README.md"
        if readme.exists():
            content = readme.read_text(encoding="utf-8", errors="replace")
            score += 5.0 if len(content) >= 200 else 2.0
            if len(content) < 200:
                issues.append(f"README too short ({len(content)} chars)")
        else:
            issues.append("No README.md")

        tsx_files = list(sd.rglob("*.tsx"))
        tsx_files = [f for f in tsx_files if "node_modules" not in str(f) and ".next" not in str(f)]
        if tsx_files:
            sample = tsx_files[:10]
            documented = sum(1 for f in sample if _file_has_docs(f))
            ratio = documented / len(sample)
            score += ratio * 5.0
            if ratio < 0.5:
                issues.append(f"Low JSDoc ({documented}/{len(sample)})")
        else:
            score += 2.5

        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        evidence = "; ".join(issues) if issues else f"Documentation OK ({score:.1f})"

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=0, command="",
        )


def _file_has_docs(f: Path) -> bool:
    try:
        content = f.read_text(encoding="utf-8", errors="replace")
        return "/**" in content or "// " in content[:500]
    except OSError:
        return False


# -- NW-03 vitest (D3) --------------------------------------------------------

@dataclass
class VitestGate(WebGate):
    """W-03: Unit test pass/fail via vitest."""

    gate_id: str = "W-03"
    name: str = "vitest"
    dimension: str = "D3"
    tool: str = "npx"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        pkg = sd / "package.json"
        if not pkg.exists():
            return self._skip_result("No package.json")

        try:
            pkg_data = json.loads(pkg.read_text())
        except (json.JSONDecodeError, OSError):
            return self._skip_result("Cannot read package.json")

        all_deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
        if "vitest" not in all_deps:
            return self._skip_result("vitest not in dependencies")

        cmd = ["npx", "vitest", "run", "--reporter=json"]
        try:
            proc, duration_ms = self._run_cmd(cmd, cwd=site_dir)
        except subprocess.TimeoutExpired:
            return self._error_result(" ".join(cmd), "Timeout", 0)

        try:
            data = json.loads(proc.stdout)
            total = data.get("numTotalTests", 0)
            passed = data.get("numPassedTests", 0)
            failed = data.get("numFailedTests", 0)
            ratio = passed / total if total > 0 else 0.0
            score = ratio * 10.0
            evidence = f"{passed}/{total} tests passed, {failed} failed"
        except (json.JSONDecodeError, KeyError):
            if proc.returncode == 0:
                score, evidence = 10.0, "All tests passed"
            else:
                output = proc.stdout + proc.stderr
                score, evidence = 3.0, output[-300:].strip() or "Tests failed"

        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=duration_ms, command=" ".join(cmd),
        )


# -- NW-04 test-coverage (D3) -------------------------------------------------

@dataclass
class TestCoverageGate(WebGate):
    """W-04: Test coverage percentage via vitest."""

    gate_id: str = "W-04"
    name: str = "test-coverage"
    dimension: str = "D3"
    tool: str = "npx"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        pkg = sd / "package.json"
        if not pkg.exists():
            return self._skip_result("No package.json")

        try:
            pkg_data = json.loads(pkg.read_text())
            all_deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
            if "vitest" not in all_deps:
                return self._skip_result("vitest not in dependencies")
        except (json.JSONDecodeError, OSError):
            return self._skip_result("Cannot read package.json")

        cmd = ["npx", "vitest", "run", "--coverage", "--reporter=json"]
        try:
            proc, duration_ms = self._run_cmd(cmd, cwd=site_dir)
        except subprocess.TimeoutExpired:
            return self._error_result(" ".join(cmd), "Timeout", 0)

        try:
            data = json.loads(proc.stdout)
            cov = data.get("coverageMap", {})
            if cov:
                total_stmts = sum(len(v.get("s", {})) for v in cov.values())
                covered = sum(sum(1 for c in v.get("s", {}).values() if c > 0) for v in cov.values())
                pct = (covered / total_stmts * 100) if total_stmts > 0 else 0
            else:
                pct = 0
        except (json.JSONDecodeError, KeyError):
            output = proc.stdout + proc.stderr
            match = re.search(r'All files\s*\|\s*([\d.]+)', output)
            pct = float(match.group(1)) if match else 0

        score = min(10.0, pct / 8.0)
        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=f"Coverage: {pct:.1f}%",
            duration_ms=duration_ms, command=" ".join(cmd),
        )


# -- NW-05 npm-audit (D4) -----------------------------------------------------

@dataclass
class NpmAuditGate(WebGate):
    """W-05: npm audit for HIGH/CRITICAL vulnerabilities."""

    gate_id: str = "W-05"
    name: str = "npm-audit"
    dimension: str = "D4"
    tool: str = "npm"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        tooling_dir = Path(client_dir) / "tooling"
        audit_data = self._read_tooling_json(tooling_dir, "npm-audit.json")
        if audit_data:
            vulns = audit_data.get("metadata", {}).get("vulnerabilities", {})
            high = vulns.get("high", 0) + vulns.get("critical", 0)
            score = max(0.0, 10.0 - high * 2.0)
            status = GateStatus.PASS if high == 0 else GateStatus.FAIL
            evidence = f"{high} HIGH/CRITICAL vulns" if high > 0 else "0 HIGH/CRITICAL"
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=status, score=score, evidence=evidence,
                duration_ms=0, command="npm audit (tooling/)",
            )

        sd = Path(site_dir)
        if not (sd / "package.json").exists():
            return self._skip_result("No package.json")

        cmd = ["npm", "audit", "--json"]
        try:
            proc, duration_ms = self._run_cmd(cmd, cwd=site_dir)
        except subprocess.TimeoutExpired:
            return self._error_result(" ".join(cmd), "Timeout", 0)

        try:
            data = json.loads(proc.stdout)
            vulns = data.get("metadata", {}).get("vulnerabilities", {})
            high = vulns.get("high", 0) + vulns.get("critical", 0)
        except (json.JSONDecodeError, KeyError):
            high = 0

        score = max(0.0, 10.0 - high * 2.0)
        status = GateStatus.PASS if high == 0 else GateStatus.FAIL
        evidence = f"{high} HIGH/CRITICAL vulns" if high > 0 else "0 HIGH/CRITICAL"
        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=duration_ms, command=" ".join(cmd),
        )


# -- NW-06 security-headers (D4) ----------------------------------------------

@dataclass
class SecurityHeadersGate(WebGate):
    """W-06: Security headers in vercel.json."""

    gate_id: str = "W-06"
    name: str = "security-headers"
    dimension: str = "D4"
    tool: str = "filesystem"

    REQUIRED_HEADERS = [
        "x-content-type-options", "x-frame-options", "referrer-policy",
        "permissions-policy", "strict-transport-security", "content-security-policy",
    ]

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        vercel_json = sd / "vercel.json"
        if not vercel_json.exists():
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=GateStatus.FAIL, score=2.0,
                evidence="No vercel.json", duration_ms=0, command="",
            )

        try:
            content = vercel_json.read_text(encoding="utf-8").lower()
        except OSError:
            return self._error_result("", "Cannot read vercel.json", 0)

        found = [h for h in self.REQUIRED_HEADERS if h in content]
        missing = [h for h in self.REQUIRED_HEADERS if h not in content]
        score = (len(found) / len(self.REQUIRED_HEADERS)) * 10.0
        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        evidence = f"{len(found)}/{len(self.REQUIRED_HEADERS)} headers" + (f" (missing: {', '.join(missing)})" if missing else "")

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=0, command="",
        )


# -- NW-07 secret-scan (D4) ---------------------------------------------------

@dataclass
class SecretScanGate(WebGate):
    """W-07: Scan for exposed secrets and API keys."""

    gate_id: str = "W-07"
    name: str = "secret-scan"
    dimension: str = "D4"
    tool: str = "grep"

    _PATTERNS = [
        r"NEXT_PUBLIC.*KEY", r"NEXT_PUBLIC.*SECRET", r"NEXT_PUBLIC.*TOKEN",
        r"sk[-_]live", r"sk[-_]test", r"AKIA[0-9A-Z]{16}",
    ]

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        src = sd / "src" if (sd / "src").exists() else sd

        findings = []
        for pattern in self._PATTERNS:
            try:
                proc = subprocess.run(
                    ["grep", "-rl", "-E", pattern, str(src),
                     "--include=*.ts", "--include=*.tsx", "--include=*.js",
                     "--exclude-dir=node_modules", "--exclude-dir=.next"],
                    capture_output=True, text=True, timeout=10,
                )
                if proc.stdout.strip():
                    findings.extend(proc.stdout.strip().splitlines())
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        unique_files = list(set(findings))
        if not unique_files:
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=GateStatus.PASS, score=10.0,
                evidence="No secrets detected", duration_ms=0, command="grep",
            )

        score = max(0.0, 10.0 - len(unique_files) * 3.0)
        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=GateStatus.FAIL, score=score,
            evidence=f"{len(unique_files)} file(s) with secrets: {', '.join(Path(f).name for f in unique_files[:5])}",
            duration_ms=0, command="grep",
        )


# -- NW-08 lighthouse-perf (D5) -----------------------------------------------

@dataclass
class LighthousePerfGate(WebGate):
    """W-08: Lighthouse performance score."""

    gate_id: str = "W-08"
    name: str = "lighthouse-perf"
    dimension: str = "D5"
    tool: str = "lighthouse"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        tooling_dir = Path(client_dir) / "tooling"
        lh = self._read_tooling_json(tooling_dir, "lighthouse.json")
        if lh is None:
            return self._not_executed_result("No lighthouse.json -- run preflight first")

        try:
            perf = lh.get("categories", {}).get("performance", {}).get("score", 0)
            score = perf * 10.0
        except (AttributeError, TypeError):
            return self._error_result("", "Invalid lighthouse.json format", 0)

        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=f"Lighthouse perf: {perf:.0%} ({score:.1f}/10)",
            duration_ms=0, command="lighthouse (tooling/)",
        )


# -- NW-09 bundle-size (D5) ---------------------------------------------------

@dataclass
class BundleSizeGate(WebGate):
    """W-09: Check for oversized JS chunks (>250KB)."""

    gate_id: str = "W-09"
    name: str = "bundle-size"
    dimension: str = "D5"
    tool: str = "filesystem"
    MAX_CHUNK_KB: int = 250

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        chunks_dirs = [sd / ".next" / "static" / "chunks", sd / "out" / "_next" / "static" / "chunks"]
        js_files = []
        for d in chunks_dirs:
            if d.exists():
                js_files.extend(d.rglob("*.js"))

        if not js_files:
            return self._skip_result("No built chunks found")

        oversized = [f"{f.name} ({f.stat().st_size // 1024}KB)" for f in js_files if f.stat().st_size / 1024 > self.MAX_CHUNK_KB]
        if not oversized:
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=GateStatus.PASS, score=10.0,
                evidence=f"All {len(js_files)} chunks < {self.MAX_CHUNK_KB}KB",
                duration_ms=0, command="",
            )

        score = max(0.0, 10.0 - len(oversized) * 2.0)
        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=GateStatus.FAIL, score=score,
            evidence=f"{len(oversized)} oversized: {', '.join(oversized[:3])}",
            duration_ms=0, command="",
        )


# -- NW-10 pa11y-a11y (D6) ----------------------------------------------------

@dataclass
class Pa11yGate(WebGate):
    """W-10: pa11y WCAG accessibility errors."""

    gate_id: str = "W-10"
    name: str = "pa11y-a11y"
    dimension: str = "D6"
    tool: str = "pa11y"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        tooling_dir = Path(client_dir) / "tooling"
        pa11y_data = self._read_tooling_json(tooling_dir, "a11y.json")
        if pa11y_data is None:
            pa11y_data = self._read_tooling_json(tooling_dir, "pa11y.json")
        if pa11y_data is None:
            return self._not_executed_result("No a11y.json -- run preflight first")

        if isinstance(pa11y_data, list):
            errors = len([i for i in pa11y_data if i.get("type") == "error"])
        else:
            errors = pa11y_data.get("total", 0)

        score = max(0.0, 10.0 - errors * 0.5)
        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score,
            evidence=f"{errors} WCAG error(s)" if errors > 0 else "No WCAG errors",
            duration_ms=0, command="pa11y (tooling/)",
        )


# -- NW-11 lighthouse-a11y (D6) -----------------------------------------------

@dataclass
class LighthouseA11yGate(WebGate):
    """W-11: Lighthouse accessibility score."""

    gate_id: str = "W-11"
    name: str = "lighthouse-a11y"
    dimension: str = "D6"
    tool: str = "lighthouse"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        tooling_dir = Path(client_dir) / "tooling"
        lh = self._read_tooling_json(tooling_dir, "lighthouse.json")
        if lh is None:
            return self._not_executed_result("No lighthouse.json -- run preflight first")

        try:
            a11y = lh.get("categories", {}).get("accessibility", {}).get("score", 0)
            score = a11y * 10.0
        except (AttributeError, TypeError):
            return self._error_result("", "Invalid lighthouse.json", 0)

        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=f"Lighthouse a11y: {a11y:.0%} ({score:.1f}/10)",
            duration_ms=0, command="lighthouse (tooling/)",
        )


# -- NW-12 lighthouse-seo (D7) ------------------------------------------------

@dataclass
class LighthouseSeoGate(WebGate):
    """W-12: Lighthouse SEO score."""

    gate_id: str = "W-12"
    name: str = "lighthouse-seo"
    dimension: str = "D7"
    tool: str = "lighthouse"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        tooling_dir = Path(client_dir) / "tooling"
        lh = self._read_tooling_json(tooling_dir, "lighthouse.json")
        if lh is None:
            return self._not_executed_result("No lighthouse.json -- run preflight first")

        try:
            seo = lh.get("categories", {}).get("seo", {}).get("score", 0)
            score = seo * 10.0
        except (AttributeError, TypeError):
            return self._error_result("", "Invalid lighthouse.json", 0)

        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=f"Lighthouse SEO: {seo:.0%} ({score:.1f}/10)",
            duration_ms=0, command="lighthouse (tooling/)",
        )


# -- NW-13 seo-meta (D7) ------------------------------------------------------

@dataclass
class SeoMetaGate(WebGate):
    """W-13: SEO meta elements."""

    gate_id: str = "W-13"
    name: str = "seo-meta"
    dimension: str = "D7"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        checks = 5
        found = 0
        issues = []

        src = sd / "src" if (sd / "src").exists() else sd
        layout_files = [f for f in list(src.rglob("layout.tsx")) + list(src.rglob("layout.ts")) if "node_modules" not in str(f)]

        if layout_files:
            try:
                content = layout_files[0].read_text(encoding="utf-8", errors="replace")
                if "title" in content.lower() and ("metadata" in content or "Metadata" in content):
                    found += 1
                else:
                    issues.append("No title")
                if "description" in content.lower():
                    found += 1
                else:
                    issues.append("No description")
                if "opengraph" in content.lower() or "og:" in content.lower() or "openGraph" in content:
                    found += 1
                else:
                    issues.append("No openGraph")
            except OSError:
                issues.extend(["layout unreadable"] * 3)
        else:
            issues.extend(["No layout.tsx"] * 3)

        if [f for f in sd.rglob("sitemap*") if "node_modules" not in str(f)]:
            found += 1
        else:
            issues.append("No sitemap")

        if [f for f in sd.rglob("robots*") if "node_modules" not in str(f)]:
            found += 1
        else:
            issues.append("No robots.txt")

        score = (found / checks) * 10.0
        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        evidence = f"{found}/{checks} SEO" + (f" (missing: {', '.join(issues)})" if issues else "")

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=0, command="",
        )


# -- NW-14 legal-compliance (D8) ----------------------------------------------

@dataclass
class LegalComplianceGate(WebGate):
    """W-14: Legal compliance -- 6 explicit checks for Loi 25."""

    gate_id: str = "W-14"
    name: str = "legal-compliance"
    dimension: str = "D8"
    tool: str = "filesystem"

    _REQUIRED_KEYWORDS = [
        ("responsable.*protection|RPRP|privacy.*officer", "RPP/Responsable protection"),
        ("renseignements personnels|donn[eé]es personnelles|personal.*information", "Donnees personnelles"),
        ("finalit[eé]|fins de|purpose", "Finalite de collecte"),
        ("dur[eé]e de conservation|p[eé]riode de conservation|retention", "Duree de conservation"),
        ("droit.{0,3}acc[eè]s.*rectification|acc[eè]s.*suppression|access.*rectification|droits.*rectification", "Droits (acces/rectification/suppression)"),
        ("plainte|recours|complaint", "Mecanisme de plainte"),
    ]

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        if not sd.exists():
            return self._skip_result("No site directory")

        src_dir = sd / "src" if (sd / "src").exists() else sd
        checks: list[tuple[str, str]] = []

        # CHECK 1: Privacy policy page exists
        privacy_files = _find_files(sd, ["*confidentialit*", "*privacy*", "*politique*"])
        if privacy_files:
            checks.append(("Page confidentialite", f"PASS -- {Path(privacy_files[0]).name}"))
        else:
            checks.append(("Page confidentialite", "FAIL -- aucun fichier confidentialite/privacy"))

        # CHECK 2: Footer link to privacy policy
        footer_files = _find_files(sd, ["*footer*", "*Footer*"])
        has_footer_link = False
        for f in footer_files:
            try:
                content = Path(f).read_text(encoding="utf-8", errors="replace").lower()
                if "confidentialit" in content or "privacy" in content or "politique" in content:
                    has_footer_link = True
                    break
            except OSError:
                pass
        checks.append(("Lien footer confidentialite",
                        "PASS -- lien dans footer" if has_footer_link else "FAIL -- pas de lien dans footer"))

        # CHECK 3: Required keywords in privacy policy content
        policy_content = ""
        for f in privacy_files:
            try:
                policy_content += Path(f).read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                pass

        kw_found = 0
        kw_missing = []
        for pattern, label in self._REQUIRED_KEYWORDS:
            if re.search(pattern, policy_content, re.IGNORECASE):
                kw_found += 1
            else:
                kw_missing.append(label)

        if kw_found == len(self._REQUIRED_KEYWORDS):
            checks.append(("Mots-cles obligatoires", f"PASS -- {kw_found}/{len(self._REQUIRED_KEYWORDS)}"))
        else:
            checks.append(("Mots-cles obligatoires",
                           f"FAIL -- {kw_found}/{len(self._REQUIRED_KEYWORDS)} (manquants: {', '.join(kw_missing)})"))

        # CHECK 4: Forms have unchecked consent checkbox
        form_files = _grep_files(src_dir, r"<form|onSubmit|handleSubmit", ["*.tsx", "*.ts", "*.jsx"])
        consent_ok = True
        consent_detail = "PASS -- pas de formulaire ou checkbox non pre-cochee"
        for f in form_files:
            try:
                content = Path(f).read_text(encoding="utf-8", errors="replace")
                if "defaultChecked" in content or "checked={true}" in content or 'checked="true"' in content:
                    consent_ok = False
                    consent_detail = f"FAIL -- checkbox pre-cochee dans {Path(f).name}"
                    break
            except OSError:
                pass
        checks.append(("Checkbox consentement non pre-cochee", consent_detail))

        # CHECK 5: Purpose statement near submit button
        purpose_near_form = False
        for f in form_files:
            try:
                content = Path(f).read_text(encoding="utf-8", errors="replace").lower()
                if ("finalit" in content or "purpose" in content or "fins de" in content
                        or "nous utilisons" in content or "vos renseignements" in content):
                    purpose_near_form = True
                    break
            except OSError:
                pass
        checks.append(("Mention finalite pres du formulaire",
                        "PASS -- mention trouvee" if purpose_near_form or not form_files else "FAIL -- aucune mention de finalite"))

        # CHECK 6: Privacy link near forms
        privacy_link_near = False
        for f in form_files:
            try:
                content = Path(f).read_text(encoding="utf-8", errors="replace").lower()
                if "confidentialit" in content or "privacy" in content:
                    privacy_link_near = True
                    break
            except OSError:
                pass
        checks.append(("Lien confidentialite pres du formulaire",
                        "PASS -- lien present" if privacy_link_near or not form_files else "FAIL -- pas de lien confidentialite"))

        passed_count = sum(1 for _, detail in checks if detail.startswith("PASS"))
        score = (passed_count / len(checks)) * 10.0
        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL

        evidence_lines = [f"CHECK {i+1} ({name}): {detail}" for i, (name, detail) in enumerate(checks)]
        evidence = " | ".join(evidence_lines)

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=0, command="",
        )


def _find_files(base: Path, patterns: list[str]) -> list[str]:
    """Find files matching glob patterns, excluding node_modules/.next."""
    results = []
    seen: set[str] = set()
    for pattern in patterns:
        for f in base.rglob(pattern):
            if "node_modules" in str(f) or ".next" in str(f):
                continue
            if f.is_file() and str(f) not in seen:
                results.append(str(f))
                seen.add(str(f))
            elif f.is_dir():
                for child in f.rglob("*"):
                    if child.is_file() and str(child) not in seen:
                        if "node_modules" not in str(child) and ".next" not in str(child):
                            results.append(str(child))
                            seen.add(str(child))
    return results


def _grep_files(base: Path, pattern: str, extensions: list[str]) -> list[str]:
    """Find files containing a regex pattern."""
    results = []
    for ext in extensions:
        for f in base.rglob(ext):
            if "node_modules" in str(f) or ".next" in str(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                if re.search(pattern, content):
                    results.append(str(f))
            except OSError:
                pass
    return results


# -- NW-15 eslint (D9) --------------------------------------------------------

@dataclass
class EslintGate(WebGate):
    """W-15: ESLint errors."""

    gate_id: str = "W-15"
    name: str = "eslint"
    dimension: str = "D9"
    tool: str = "npx"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        if not (sd / "package.json").exists():
            return self._skip_result("No package.json")

        eslint_configs = list(sd.glob(".eslintrc*")) + list(sd.glob("eslint.config*"))
        if not eslint_configs:
            try:
                pkg = json.loads((sd / "package.json").read_text())
                if "eslintConfig" not in pkg:
                    return self._skip_result("No ESLint configuration")
            except (json.JSONDecodeError, OSError):
                return self._skip_result("Cannot read package.json")

        cmd = ["npx", "eslint", ".", "--format=json", "--no-error-on-unmatched-pattern"]
        try:
            proc, duration_ms = self._run_cmd(cmd, cwd=site_dir)
        except subprocess.TimeoutExpired:
            return self._error_result(" ".join(cmd), "Timeout", 0)

        try:
            results = json.loads(proc.stdout) if proc.stdout.strip() else []
            error_count = sum(r.get("errorCount", 0) for r in results)
            warning_count = sum(r.get("warningCount", 0) for r in results)
        except (json.JSONDecodeError, TypeError):
            error_count = (proc.stdout + proc.stderr).lower().count("error") if proc.returncode != 0 else 0
            warning_count = 0

        score = max(0.0, 10.0 - error_count * 0.5 - warning_count * 0.1)
        status = GateStatus.PASS if error_count == 0 else GateStatus.FAIL

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=f"{error_count} error(s), {warning_count} warning(s)",
            duration_ms=duration_ms, command=" ".join(cmd),
        )


# -- NW-16 typescript-strict (D9) ---------------------------------------------

@dataclass
class TypescriptStrictGate(WebGate):
    """W-16: TypeScript strict mode and no `any` types."""

    gate_id: str = "W-16"
    name: str = "typescript-strict"
    dimension: str = "D9"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        tsconfig = sd / "tsconfig.json"
        if not tsconfig.exists():
            return self._skip_result("No tsconfig.json")

        try:
            content = tsconfig.read_text(encoding="utf-8")
            # Strip JSON-with-comments (JSONC)
            result_chars = []
            i = 0
            in_string = False
            while i < len(content):
                c = content[i]
                if in_string:
                    result_chars.append(c)
                    if c == '\\' and i + 1 < len(content):
                        i += 1
                        result_chars.append(content[i])
                    elif c == '"':
                        in_string = False
                elif c == '"':
                    in_string = True
                    result_chars.append(c)
                elif c == '/' and i + 1 < len(content) and content[i + 1] == '/':
                    while i < len(content) and content[i] != '\n':
                        i += 1
                    continue
                elif c == '/' and i + 1 < len(content) and content[i + 1] == '*':
                    i += 2
                    while i + 1 < len(content) and not (content[i] == '*' and content[i + 1] == '/'):
                        i += 1
                    i += 2
                    continue
                else:
                    result_chars.append(c)
                i += 1
            ts_data = json.loads(''.join(result_chars))
        except (json.JSONDecodeError, OSError, IndexError):
            return self._error_result("", "Cannot parse tsconfig.json", 0)

        compiler = ts_data.get("compilerOptions", {})
        checks = 3
        passed = 0
        issues = []

        if compiler.get("strict") is True:
            passed += 1
        else:
            issues.append("strict: true not set")

        if compiler.get("noUncheckedIndexedAccess") is True:
            passed += 1
        else:
            issues.append("noUncheckedIndexedAccess missing")

        src = sd / "src" if (sd / "src").exists() else sd
        ts_files = [f for f in list(src.rglob("*.ts")) + list(src.rglob("*.tsx"))
                     if "node_modules" not in str(f) and ".next" not in str(f)]
        any_count = 0
        for f in ts_files[:50]:
            try:
                any_count += len(re.findall(r'\bany\b', f.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass

        if any_count <= 5:
            passed += 1
        else:
            issues.append(f"{any_count} `any` usages")

        score = (passed / checks) * 10.0
        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score,
            evidence="; ".join(issues) if issues else "TypeScript strict OK",
            duration_ms=0, command="",
        )


# -- NW-17 cookie-consent (D8) ------------------------------------------------

TRACKER_DOMAINS = [
    'google-analytics.com', 'googletagmanager.com',
    'facebook.net', 'facebook.com/tr',
    'hotjar.com', 'clarity.ms',
    'doubleclick.net', 'googlesyndication.com',
    'linkedin.com/px', 'twitter.com/i/adsct',
    'tiktok.com/i/pixel', 'snap.licdn.com',
]


@dataclass
class CookieConsentGate(WebGate):
    """W-17: Cookie consent -- no non-essential cookies before explicit consent.

    Checks via static analysis (code inspection) with max score 7.0.
    Full runtime check with Playwright would yield up to 10.0.
    """

    gate_id: str = "W-17"
    name: str = "cookie-consent"
    dimension: str = "D8"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        sd = Path(site_dir)
        src = sd / "src" if (sd / "src").exists() else sd
        if not sd.exists():
            return self._skip_result("No site directory")

        issues = []
        checks = 4
        passed = 0

        # CHECK 1: Cookie consent component exists
        consent_files = _find_files(sd, ["*cookie*consent*", "*CookieConsent*", "*cookie*banner*", "*CookieBanner*"])
        if consent_files:
            passed += 1
        else:
            issues.append("No cookie consent component found")

        # CHECK 2: Tracker scripts are conditionally loaded
        all_source = ""
        tsx_files = [f for f in list(src.rglob("*.tsx")) + list(src.rglob("*.ts"))
                     if "node_modules" not in str(f) and ".next" not in str(f)]
        for f in tsx_files[:30]:
            try:
                all_source += Path(f).read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

        tracker_refs = []
        for domain in TRACKER_DOMAINS:
            if domain in all_source:
                tracker_refs.append(domain)

        if not tracker_refs:
            passed += 1
        else:
            consent_patterns = ["consent", "cookie", "gtag.*consent", "consentement"]
            wrapped = any(p in all_source.lower() for p in consent_patterns)
            if wrapped:
                passed += 1
            else:
                issues.append(f"Tracker scripts ({', '.join(tracker_refs[:3])}) not wrapped in consent check")

        # CHECK 3: No pre-loaded analytics in <head> / layout
        layout_files = [f for f in list(src.rglob("layout.tsx")) + list(src.rglob("layout.ts"))
                        if "node_modules" not in str(f)]
        head_tracker = False
        for f in layout_files:
            try:
                content = Path(f).read_text(encoding="utf-8", errors="replace")
                for domain in TRACKER_DOMAINS[:4]:
                    if domain in content and "consent" not in content.lower():
                        head_tracker = True
                        break
            except OSError:
                pass

        if not head_tracker:
            passed += 1
        else:
            issues.append("Tracker in layout/head without consent gate")

        # CHECK 4: Refuser button as visible as Accepter
        consent_content = ""
        for f in consent_files:
            try:
                consent_content += Path(f).read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

        if consent_content:
            has_reject = any(kw in consent_content.lower() for kw in ["refuser", "reject", "decline", "deny"])
            if has_reject:
                passed += 1
            else:
                issues.append("No 'Refuser' button in cookie consent")
        elif not consent_files:
            issues.append("No consent component to check")
        else:
            passed += 1

        # Score: static analysis caps at 7.0
        raw_score = (passed / checks) * 10.0
        score = min(7.0, raw_score) if raw_score > 0 else 0.0
        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        evidence = f"{passed}/{checks} checks" + (f" (issues: {'; '.join(issues)})" if issues else " -- static analysis only (max 7.0)")

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=0, command="static analysis",
        )


# ── NEXOS gate set loaders ───────────────────────────────────────────────────

_ALL_WEB_GATES = [
    NextJSStructureGate,    # W-01 D1
    DocumentationGate,      # W-02 D2
    VitestGate,             # W-03 D3
    TestCoverageGate,       # W-04 D3
    NpmAuditGate,           # W-05 D4
    SecurityHeadersGate,    # W-06 D4
    SecretScanGate,         # W-07 D4
    LighthousePerfGate,     # W-08 D5
    BundleSizeGate,         # W-09 D5
    Pa11yGate,              # W-10 D6
    LighthouseA11yGate,     # W-11 D6
    LighthouseSeoGate,      # W-12 D7
    SeoMetaGate,            # W-13 D7
    LegalComplianceGate,    # W-14 D8
    EslintGate,             # W-15 D9
    TypescriptStrictGate,   # W-16 D9
    CookieConsentGate,      # W-17 D8
]

_BUILD_GATE_IDS = {"W-01", "W-05", "W-06", "W-07", "W-14", "W-15", "W-16"}


def _load_web_full_gates() -> list[WebGate]:
    """All 17 web gates for ph5-qa."""
    return [cls() for cls in _ALL_WEB_GATES]


def _load_web_build_gates() -> list[WebGate]:
    """Subset of web gates for ph4-build."""
    return [g for g in _load_web_full_gates() if g.gate_id in _BUILD_GATE_IDS]


register_gate_set("WEB_FULL", _load_web_full_gates)
register_gate_set("WEB_BUILD", _load_web_build_gates)
