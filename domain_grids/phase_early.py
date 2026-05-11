"""SOIC v3.0 — PHASE_EARLY: lightweight gates for phases 0-3.

These gates evaluate the phase report (no site exists yet).

Gate inventory:
- PE-01..PE-04: generic report-quality gates (D1, D2). Run for any phase.
- PE-05..PE-09: ph0-discovery specific gates (D2, D3, D6, D7, D9). Read
  ``ph0-discovery-report.md`` directly; SKIP if absent. Together with
  PE-01..PE-04 they expand the dimensional coverage of ph0 from D1+D2 to
  six dimensions (D1, D2, D3, D6, D7, D9), fixing the historical
  structural plateau where partial coverage capped μ at ~6.11
  (cf. BUG_SOIC_PH0_GATES_INCOMPLETS.md). The original SESSION_02 mapping
  used D5 (Performance) for UX patterns and D6 (Accessibilité) for content
  gaps — semantically incorrect; SESSION_04.5 of chantier mode B remapped
  PE-06 D5→D6 and PE-07 D6→D2 so the dimension labels match the gate
  subjects (cf. phase-04.5-report.md).
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


def _get_ph0_report(client_dir: str) -> str:
    """Read ``ph0-discovery-report.md`` strictly (no fallback)."""
    path = Path(client_dir) / _REPORT_MAP["ph0-discovery"]
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# Tech stack keywords used by PE-05 to count distinct technologies cited.
_STACK_KEYWORDS = (
    r"Next\.?js|React|Vue|Angular|Svelte|Astro|Remix|Nuxt|"
    r"Tailwind|TypeScript|JavaScript|Node\.?js|Deno|Bun|"
    r"Vercel|Netlify|Cloudflare|AWS|Azure|GCP|"
    r"PostgreSQL|MySQL|MongoDB|Redis|Supabase|Firebase|"
    r"Docker|Kubernetes|Python|Django|FastAPI|Flask|Express|"
    r"GraphQL|REST|gRPC|"
    r"WordPress|Shopify|Webflow|Wix|Squarespace|Drupal|"
    r"Eleventy|Jekyll|Hugo|Gatsby|Elementor"
)


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
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.FAIL,
                score=0.0,
                evidence="No report found",
                duration_ms=0,
                command="",
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
        evidence = (
            "; ".join(issues)
            if issues
            else f"Report complete ({len(content)} chars, {len(headings)} sections)"
        )

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=status,
            score=score,
            evidence=evidence,
            duration_ms=0,
            command="",
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
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.FAIL,
                score=0.0,
                evidence="No report found",
                duration_ms=0,
                command="",
            )

        # A-008 fix : accepter aussi 'éditorial', 'qualitatif', 'discovery', 'stratégique', 'phase'
        # — synonymes métier utilisés dans les templates NEXOS sans contraindre le wording.
        # `[\s*]*` au lieu de `\s*` accepte aussi le markdown bold `**` autour des séparateurs
        # (ex: `**Score éditorial** : **7.8 / 10**`).
        score_labels = (
            "global",
            "[ée]ditorial",
            "qualitatif",
            "discovery",
            "strat[ée]gique",
            "phase",
        )
        pattern = rf"(?:score[\s*]*(?:{'|'.join(score_labels)})|[μm])[\s*]*[:=][\s*]*(\d+\.?\d*)[\s*]*/?[\s*]*10"
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.PASS,
                score=10.0,
                evidence=f"Score found: {match.group(0)}",
                duration_ms=0,
                command="",
            )

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=GateStatus.FAIL,
            score=3.0,
            evidence="No 'Score (global|éditorial|qualitatif|discovery|stratégique|phase): X/10' pattern found",
            duration_ms=0,
            command="",
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
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.FAIL,
                score=0.0,
                evidence="No report found",
                duration_ms=0,
                command="",
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
        evidence = f"{found}/{len(expected)} sections found" + (
            f" (missing: {', '.join(missing)})" if missing else ""
        )

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=status,
            score=score,
            evidence=evidence,
            duration_ms=0,
            command="",
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
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.FAIL,
                score=0.0,
                evidence="No report found",
                duration_ms=0,
                command="",
            )

        placeholders = re.findall(
            r"\[(?:TODO|TBD|INSERT|PLACEHOLDER|XXX|FIXME)[^\]]*\]", content, re.IGNORECASE
        )
        count = len(placeholders)

        if count == 0:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.PASS,
                score=10.0,
                evidence="No placeholders found",
                duration_ms=0,
                command="",
            )

        score = max(0.0, 10.0 - count * 2.0)
        examples = ", ".join(placeholders[:3])
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=GateStatus.FAIL,
            score=score,
            evidence=f"{count} placeholder(s) found: {examples}",
            duration_ms=0,
            command="",
        )


@dataclass
class StackDetectedGate(WebGate):
    """PE-05: ph0 report identifies the sector stack (technos + perf/sec)."""

    gate_id: str = "PE-05"
    name: str = "report-stack-detected"
    dimension: str = "D3"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        content = _get_ph0_report(client_dir)
        if not content:
            return self._skip_result("ph0-discovery-report.md not present")

        # Section §3 (tech-inspector / stack) — heuristics: numbered heading,
        # explicit "tech-inspector" or "stack" wording.
        section_present = bool(
            re.search(r"(?im)^#{1,3}\s*§?\s*3[\.\s]", content)
            or re.search(r"(?i)tech[- ]inspector|stack\s+(?:technique|d[ée]tect)", content)
        )
        if not section_present:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.FAIL,
                score=2.0,
                evidence="No §3 / tech-inspector / stack section detected",
                duration_ms=0,
                command="",
            )

        techs = re.findall(rf"\b(?:{_STACK_KEYWORDS})\b", content, flags=re.IGNORECASE)
        n_distinct = len({t.lower() for t in techs})
        perf_sec_mentioned = bool(
            re.search(r"(?i)\b(perf|performance|s[ée]curit[ée]|security|hsts|csp)\b", content)
        )

        if n_distinct >= 3 and perf_sec_mentioned:
            score, evidence = 10.0, f"{n_distinct} technologies + perf/sec mentioned"
            status = GateStatus.PASS
        elif n_distinct >= 2:
            score, evidence = 7.5, f"{n_distinct} technologies identified"
            status = GateStatus.PASS
        elif n_distinct >= 1:
            score, evidence = 5.0, "1 technology mentioned, depth limited"
            status = GateStatus.FAIL
        else:
            score, evidence = 2.0, "No clear technology identified"
            status = GateStatus.FAIL

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=status,
            score=score,
            evidence=evidence,
            duration_ms=0,
            command="",
        )


@dataclass
class UxPatternsGate(WebGate):
    """PE-06: ph0 report lists UX patterns + anti-patterns + a11y.

    Dimension mapping: D6 Accessibilité — UX patterns analysis explicitly
    covers a11y (WCAG, contrast, keyboard, ARIA, prefers-reduced-motion),
    so the gate naturally fits the Accessibilité dimension. Was D5
    (Performance) prior to SESSION_04.5 of chantier mode B — corrected as
    a semantic mismatch (cf. phase-04.5-report.md).
    """

    gate_id: str = "PE-06"
    name: str = "report-ux-patterns"
    dimension: str = "D6"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        content = _get_ph0_report(client_dir)
        if not content:
            return self._skip_result("ph0-discovery-report.md not present")

        section_present = bool(
            re.search(r"(?im)^#{1,3}\s*§?\s*4[\.\s]", content)
            or re.search(r"(?i)ux[- ]analyst|patterns?\s+ux|patterns?\s+dominants?", content)
        )
        if not section_present:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.FAIL,
                score=2.0,
                evidence="No §4 / ux-analyst / UX patterns section detected",
                duration_ms=0,
                command="",
            )

        patterns = re.findall(r"\bP\d{2}\b", content)
        n_patterns = len(set(patterns))
        anti_patterns = re.findall(r"(?i)anti[- ]pattern", content)
        n_anti = len(anti_patterns)
        a11y = bool(
            re.search(
                r"(?i)wcag|a11y|accessibili|contraste|clavier|aria|touch[- ]target|prefers[- ]reduced[- ]motion",
                content,
            )
        )

        if n_patterns >= 5 and a11y:
            score, evidence = 10.0, f"{n_patterns} patterns + a11y detailed"
            status = GateStatus.PASS
        elif n_patterns >= 3 and n_anti >= 1:
            score, evidence = 7.5, f"{n_patterns} patterns + {n_anti} anti-patterns"
            status = GateStatus.PASS
        elif n_patterns >= 1:
            score, evidence = 5.0, f"{n_patterns} pattern(s) — coverage thin"
            status = GateStatus.FAIL
        else:
            score, evidence = 2.0, "No P## pattern code detected"
            status = GateStatus.FAIL

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=status,
            score=score,
            evidence=evidence,
            duration_ms=0,
            command="",
        )


@dataclass
class ContentGapsGate(WebGate):
    """PE-07: ph0 report identifies content gaps / TBD / kickoff blockers.

    Dimension mapping: D2 Documentation — variables bloquantes, TBD markers
    and kickoff blockers are documentation artefacts of the discovery
    output (what is known vs what must still be collected from the
    client). Was D6 (Accessibilité) prior to SESSION_04.5 of chantier
    mode B — corrected as a semantic mismatch (cf. phase-04.5-report.md).
    """

    gate_id: str = "PE-07"
    name: str = "report-content-gaps"
    dimension: str = "D2"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        content = _get_ph0_report(client_dir)
        if not content:
            return self._skip_result("ph0-discovery-report.md not present")

        section_present = bool(
            re.search(r"(?im)^#{1,3}\s*§?\s*5[\.\s]", content)
            or re.search(
                r"(?i)content[- ]evaluator|contenu\s+existant|gaps?\s+de\s+contenu", content
            )
        )

        # Count blocker indicators: TBD/[bracket placeholder]/bloquante(s)/kickoff
        blockers = re.findall(
            r"(?i)\bTBD\b|\[\s*(?:TBD|TODO|INSERT|PLACEHOLDER|XXX|FIXME|"
            r"ville|adresse|t[ée]l[ée]phone|horaires?|NEQ)\b[^\]]*\]|"
            r"\b(?:bloquant|bloquante)s?\b|"
            r"\bvariables?\s+(?:bloquant|[àa]\s+fixer)|"
            r"\bkickoff\b",
            content,
        )
        n_blockers = len(blockers)

        if not section_present and n_blockers == 0:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.FAIL,
                score=2.0,
                evidence="No §5 content section and no blocker markers",
                duration_ms=0,
                command="",
            )

        # Bonus signal: a structured list of variables to fix
        structured = bool(
            re.search(r"(?ims)variables?\s+bloquantes?.*?(?:\n[\s\-\*\d]{1,5}.+){3,}", content)
        )

        if n_blockers >= 5 and structured:
            score, evidence = 10.0, f"{n_blockers} blocker hits + structured list"
            status = GateStatus.PASS
        elif n_blockers >= 3:
            score, evidence = 7.5, f"{n_blockers} blocker hits"
            status = GateStatus.PASS
        elif n_blockers >= 1:
            score, evidence = 5.0, f"{n_blockers} blocker hit — content gaps thin"
            status = GateStatus.FAIL
        else:
            score, evidence = 3.0, "Section present but no blockers identified"
            status = GateStatus.FAIL

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=status,
            score=score,
            evidence=evidence,
            duration_ms=0,
            command="",
        )


@dataclass
class PositioningGate(WebGate):
    """PE-08: ph0 report articulates positioning + actionable recommendations."""

    gate_id: str = "PE-08"
    name: str = "report-positioning"
    dimension: str = "D7"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        content = _get_ph0_report(client_dir)
        if not content:
            return self._skip_result("ph0-discovery-report.md not present")

        positioning = bool(re.search(r"(?i)\bpositionnement\b|\bpositioning\b", content))
        if not positioning:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.FAIL,
                score=2.0,
                evidence="No 'positionnement' keyword found",
                duration_ms=0,
                command="",
            )

        # Look for an actionable recommendations block: a "Recommandations"
        # H1/H2 heading followed by numbered/bulleted action items. We only
        # break the block on H1/H2 boundaries so that H3 sub-sections inside
        # the recommendations stay captured.
        reco_block = re.search(
            r"(?ims)^#{1,2}\s*[^\n]*recommandations?[^\n]*$(.+?)(?=^#{1,2}\s|\Z)",
            content,
        )
        action_items = 0
        if reco_block:
            action_items = len(
                re.findall(
                    r"(?im)^\s*(?:[-*]|\d+\.)\s+\S",
                    reco_block.group(1),
                )
            )

        # SMART/quantitative signal: numbered targets, deadlines, units
        smart = bool(
            re.search(
                r"(?i)\b(?:\d+\s?(?:%|min|sec|s|ms|kb|mb|/\d+)|"
                r"phase\s+\d+|kpi|score\s*[:=]\s*\d|μ\s*[≥>=]\s*\d)\b",
                content,
            )
        )

        if action_items >= 3 and smart:
            score, evidence = 10.0, f"positioning + {action_items} action items + SMART signals"
            status = GateStatus.PASS
        elif action_items >= 2:
            score, evidence = 7.5, f"positioning + {action_items} action items"
            status = GateStatus.PASS
        elif action_items >= 1:
            score, evidence = 5.0, "positioning + 1 action item only"
            status = GateStatus.FAIL
        else:
            score, evidence = 4.0, "positioning mentioned but no actionable recommendations block"
            status = GateStatus.FAIL

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=status,
            score=score,
            evidence=evidence,
            duration_ms=0,
            command="",
        )


@dataclass
class CompetitiveGapsGate(WebGate):
    """PE-09: ph0 report names competitors and articulates differentiation gaps.

    Dimension mapping (extended): D9 Code Quality is used in ph0-discovery
    as a proxy for "qualité distinctive du livrable". The competitive-gaps
    analysis is a signal of qualitative differentiation of the diagnostic,
    by analogy with code quality in later phases (D9 measures distinctness
    and rigor). Documented and accepted as a stretched mapping in
    SESSION_04.5 of chantier mode B (cf. phase-04.5-report.md).
    """

    gate_id: str = "PE-09"
    name: str = "report-competitive-gaps"
    dimension: str = "D9"
    tool: str = "filesystem"

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        content = _get_ph0_report(client_dir)
        if not content:
            return self._skip_result("ph0-discovery-report.md not present")

        gaps_keyword = bool(
            re.search(r"(?i)\b(?:gaps?|diff[ée]renciation|[ée]carts?|opportunit[ée]s?)\b", content)
        )
        if not gaps_keyword:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                dimension=self.dimension,
                status=GateStatus.FAIL,
                score=2.0,
                evidence="No gaps / différenciation / écarts keyword",
                duration_ms=0,
                command="",
            )

        # Count distinct competitors. We accept either "C1..Cn" archetype tags
        # (the ph0 template convention) or "Concurrent N" mentions.
        competitor_tags = re.findall(r"\bC[1-9]\b", content)
        n_tags = len(set(competitor_tags))
        concurrents = re.findall(r"(?i)\bconcurrent\s*\d+\b", content)
        n_concurrents = max(n_tags, len(set(concurrents)))

        # Bonus: a forces/faiblesses or gaps matrix table
        matrix = bool(
            re.search(
                r"(?i)\bmatrice\b.*?(?:gaps?|forces?|faiblesses?|diff[ée]renciation)|"
                r"\|\s*Axe\s*\|.*?\bgap",
                content,
            )
        )

        if n_concurrents >= 5 and matrix:
            score, evidence = 10.0, f"{n_concurrents} competitors + gaps matrix"
            status = GateStatus.PASS
        elif n_concurrents >= 3:
            score, evidence = 7.5, f"{n_concurrents} competitors + gaps keyword"
            status = GateStatus.PASS
        elif n_concurrents >= 1:
            score, evidence = 5.0, f"{n_concurrents} competitor(s) — benchmark thin"
            status = GateStatus.FAIL
        else:
            score, evidence = 3.0, "gaps keyword but no concrete competitors"
            status = GateStatus.FAIL

        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            dimension=self.dimension,
            status=status,
            score=score,
            evidence=evidence,
            duration_ms=0,
            command="",
        )


def _load_phase_early_gates() -> list[WebGate]:
    return [
        ReportCompletenessGate(),
        ReportScorePresentGate(),
        ReportSectionsGate(),
        NoPlaceholdersGate(),
        StackDetectedGate(),
        UxPatternsGate(),
        ContentGapsGate(),
        PositioningGate(),
        CompetitiveGapsGate(),
    ]


register_gate_set("PHASE_EARLY", _load_phase_early_gates)
