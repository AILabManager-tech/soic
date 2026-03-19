"""SOIC v3.0 — Report generation."""

from datetime import datetime
from pathlib import Path

from .dimensions import DIMENSIONS, calculate_mu
from .models import GateStatus, PhaseGateReport


def generate_report(scores: dict[str, float], client_dir: Path) -> str:
    """Generate a SOIC report in Markdown format (legacy)."""
    mu = calculate_mu(scores)

    lines = [
        "# Rapport SOIC v3.0",
        f"\n**Date** : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Client** : {client_dir.name}",
        f"**mu global** : {mu:.2f}/10.0",
        "",
        "## Scores par dimension",
        "",
        "| Dimension | Score | Poids | Description |",
        "|-----------|-------|-------|-------------|",
    ]

    for dim_id, dim_info in DIMENSIONS.items():
        score = scores.get(dim_id, 0.0)
        status = "+" if score >= 8.0 else "~" if score >= 6.0 else "-"
        lines.append(
            f"| {status} {dim_id} {dim_info['name']} | {score:.1f}/10 "
            f"| x{dim_info['weight']} | {dim_info['description']} |"
        )

    lines.extend([
        "",
        f"## Verdict : {'PASS' if mu >= 8.5 else 'FAIL'}",
        f"mu = {mu:.2f} {'>=  ' if mu >= 8.5 else '<'} 8.5",
    ])

    return "\n".join(lines)


_STATUS_ICONS = {
    "PASS": "+",
    "FAIL": "-",
    "SKIP": "~",
    "ERROR": "!",
    "NOT_EXECUTED": "?",
}


def generate_report_v2(report: PhaseGateReport) -> str:
    """Generate a detailed SOIC v3.0 report from a PhaseGateReport.

    Includes per-gate details, coverage indicator, and dimension breakdown.
    """
    cov_pct = report.coverage * 100
    if report.coverage >= 0.7:
        cov_label = f"Coverage: {cov_pct:.0f}%"
    else:
        cov_label = f"Coverage: {cov_pct:.0f}% -- INCOMPLETE (< 70%)"

    lines = [
        "# Rapport SOIC v3.0",
        f"\n**Date** : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Client** : {report.client_slug}",
        f"**Phase** : {report.phase}",
        f"**Iteration** : {report.iteration}",
        f"**mu global** : {report.mu:.2f}/10.0",
        f"**{cov_label}**",
        "",
        "## Scores par dimension",
        "",
        "| Dimension | Score | Poids | Description |",
        "|-----------|-------|-------|-------------|",
    ]

    for dim_id, dim_info in DIMENSIONS.items():
        score = report.dimension_scores.get(dim_id, 0.0)
        icon = "+" if score >= 8.0 else "~" if score >= 6.0 else "-"
        lines.append(
            f"| {icon} {dim_id} {dim_info['name']} | {score:.1f}/10 "
            f"| x{dim_info['weight']} | {dim_info['description']} |"
        )

    lines.extend([
        "",
        "## Detail des gates",
        "",
        "| Gate | Dimension | Status | Score | Evidence |",
        "|------|-----------|--------|-------|----------|",
    ])

    for g in report.gates:
        icon = _STATUS_ICONS.get(g.status.value, "?")
        evidence_short = g.evidence[:80] + "..." if len(g.evidence) > 80 else g.evidence
        lines.append(
            f"| {icon} {g.gate_id} {g.name} | {g.dimension} | {g.status.value} "
            f"| {g.score:.1f} | {evidence_short} |"
        )

    passed = sum(1 for g in report.gates if g.status == GateStatus.PASS)
    failed = sum(1 for g in report.gates if g.status in (GateStatus.FAIL, GateStatus.ERROR))
    skipped = sum(1 for g in report.gates if g.status == GateStatus.SKIP)
    not_exec = sum(1 for g in report.gates if g.status == GateStatus.NOT_EXECUTED)

    verdict = "PASS" if report.mu >= 8.5 and report.coverage >= 0.7 else "FAIL"
    if report.coverage < 0.7:
        verdict = "INCOMPLETE"

    lines.extend([
        "",
        f"## Verdict : {verdict}",
        f"mu = {report.mu:.2f} | {passed} PASS, {failed} FAIL, {skipped} SKIP, {not_exec} NOT_EXECUTED",
    ])

    return "\n".join(lines)
