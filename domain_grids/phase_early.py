"""SOIC v3.0 — PHASE_EARLY: 4 lightweight gates for phases 0-3.

These gates evaluate the phase report (no site exists yet).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import register_gate_set
from ..gate_protocol import WebGate
from ..models import GateResult, GateStatus

# Expected report files per phase
_REPORT_MAP = {
    "ph0-discovery": "ph0-discovery-report.md",
    "ph1-strategy": "ph1-strategy-report.md",
    "ph2-design": "ph2-design-report.md",
    "ph3-content": "ph3-content-report.md",
}

# Expected sections by phase (subset for validation)
_EXPECTED_SECTIONS = {
    "ph0-discovery": ["industrie", "concurren", "cible", "recommandation"],
    "ph1-strategy": ["objectif", "persona", "architecture", "contenu"],
    "ph2-design": ["palette", "typograph", "composant", "layout"],
    "ph3-content": ["page", "seo", "ton", "contenu"],
}


def _get_report_content(client_dir: str, phase: str = "") -> str:
    """Read the most recent phase report from the client directory."""
    cdir = Path(client_dir)
    if phase and phase in _REPORT_MAP:
        path = cdir / _REPORT_MAP[phase]
        if path.exists():
            return path.read_text(encoding="utf-8")

    # Fallback: find the most recent report
    for name in reversed(list(_REPORT_MAP.values())):
        path = cdir / name
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


@dataclass
class ReportCompletenessGate(WebGate):
    """PE-01: Report is substantial and well-structured."""

    gate_id: str = "PE-01"
    name: str = "report-completeness"
    dimension: str = "D2"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        content = _get_report_content(client_dir)
        if not content:
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=GateStatus.FAIL, score=0.0,
                evidence="No report found", duration_ms=0, command="",
            )

        issues = []
        score = 10.0

        if len(content) < 500:
            issues.append(f"Report too short ({len(content)} chars < 500)")
            score -= 4.0
        elif len(content) < 1000:
            score -= 1.0

        headings = re.findall(r"^#{1,3}\s+.+", content, re.MULTILINE)
        if len(headings) < 3:
            issues.append(f"Only {len(headings)} headings (need >= 3)")
            score -= 3.0

        score = max(0.0, score)
        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        evidence = "; ".join(issues) if issues else f"Report complete ({len(content)} chars, {len(headings)} sections)"

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=0, command="",
        )


@dataclass
class ReportScorePresentGate(WebGate):
    """PE-02: Report contains a 'Score global: X/10' line."""

    gate_id: str = "PE-02"
    name: str = "report-score-present"
    dimension: str = "D1"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        content = _get_report_content(client_dir)
        if not content:
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=GateStatus.FAIL, score=0.0,
                evidence="No report found", duration_ms=0, command="",
            )

        pattern = r'(?:score\s*global|[μm])\s*[:=]\s*(\d+\.?\d*)\s*/?\s*10'
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=GateStatus.PASS, score=10.0,
                evidence=f"Score found: {match.group(0)}", duration_ms=0, command="",
            )

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=GateStatus.FAIL, score=3.0,
            evidence="No 'Score global: X/10' pattern found", duration_ms=0, command="",
        )


@dataclass
class ReportSectionsGate(WebGate):
    """PE-03: Report contains expected sections for the phase template."""

    gate_id: str = "PE-03"
    name: str = "report-sections"
    dimension: str = "D1"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        content = _get_report_content(client_dir)
        if not content:
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=GateStatus.FAIL, score=0.0,
                evidence="No report found", duration_ms=0, command="",
            )

        content_lower = content.lower()

        cdir = Path(client_dir)
        phase = ""
        for ph, fname in _REPORT_MAP.items():
            if (cdir / fname).exists():
                phase = ph

        expected = _EXPECTED_SECTIONS.get(phase, _EXPECTED_SECTIONS["ph0-discovery"])
        found = sum(1 for kw in expected if kw in content_lower)
        ratio = found / len(expected) if expected else 1.0
        score = ratio * 10.0

        status = GateStatus.PASS if score >= 7.0 else GateStatus.FAIL
        missing = [kw for kw in expected if kw not in content_lower]
        evidence = (
            f"{found}/{len(expected)} sections found"
            + (f" (missing: {', '.join(missing)})" if missing else "")
        )

        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=status, score=score, evidence=evidence,
            duration_ms=0, command="",
        )


@dataclass
class NoPlaceholdersGate(WebGate):
    """PE-04: Report has no leftover placeholders."""

    gate_id: str = "PE-04"
    name: str = "no-placeholders"
    dimension: str = "D2"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        content = _get_report_content(client_dir)
        if not content:
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=GateStatus.FAIL, score=0.0,
                evidence="No report found", duration_ms=0, command="",
            )

        placeholders = re.findall(r'\[(?:TODO|TBD|INSERT|PLACEHOLDER|XXX|FIXME)[^\]]*\]', content, re.IGNORECASE)
        count = len(placeholders)

        if count == 0:
            return GateResult(
                gate_id=self.gate_id, name=self.name, dimension=self.dimension,
                status=GateStatus.PASS, score=10.0,
                evidence="No placeholders found", duration_ms=0, command="",
            )

        score = max(0.0, 10.0 - count * 2.0)
        examples = ", ".join(placeholders[:3])
        return GateResult(
            gate_id=self.gate_id, name=self.name, dimension=self.dimension,
            status=GateStatus.FAIL, score=score,
            evidence=f"{count} placeholder(s) found: {examples}", duration_ms=0, command="",
        )


def _load_phase_early_gates() -> list[WebGate]:
    return [
        ReportCompletenessGate(),
        ReportScorePresentGate(),
        ReportSectionsGate(),
        NoPlaceholdersGate(),
    ]


register_gate_set("PHASE_EARLY", _load_phase_early_gates)
