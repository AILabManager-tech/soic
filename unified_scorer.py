"""SOIC v3.0 — Unified Scorer: combines OSIRIS weighted score and SOIC gate score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class UnifiedScore:
    """Combined OSIRIS + SOIC score."""

    osiris_score: float
    osiris_grade: str
    soic_mu: float
    soic_pass_rate: float
    coherence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "osiris_score": self.osiris_score,
            "osiris_grade": self.osiris_grade,
            "soic_mu": self.soic_mu,
            "soic_pass_rate": self.soic_pass_rate,
            "coherence": self.coherence,
        }


def compute_unified_score(
    osiris_score: float,
    osiris_grade: str,
    soic_mu: float,
    soic_pass_rate: float,
) -> UnifiedScore:
    """Compute a unified score from both scoring systems.

    Args:
        osiris_score: OSIRIS weighted composite score (0-10).
        osiris_grade: OSIRIS grade string.
        soic_mu: SOIC gate-based score mu (0-10).
        soic_pass_rate: SOIC pass rate (0.0-1.0).

    Returns:
        UnifiedScore with coherence measure.
    """
    # Coherence = 1 - |delta| / 10
    # Measures how aligned the two scoring systems are (1.0 = perfect alignment)
    delta = abs(osiris_score - soic_mu)
    coherence = max(0.0, 1.0 - delta / 10.0)

    return UnifiedScore(
        osiris_score=round(osiris_score, 2),
        osiris_grade=osiris_grade,
        soic_mu=round(soic_mu, 2),
        soic_pass_rate=round(soic_pass_rate, 4),
        coherence=round(coherence, 4),
    )


def format_unified_report(score: UnifiedScore) -> str:
    """Format a unified score as a human-readable report section."""
    lines = [
        "## Unified Score",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| OSIRIS Score | {score.osiris_score}/10 ({score.osiris_grade}) |",
        f"| SOIC mu | {score.soic_mu}/10 |",
        f"| SOIC Pass Rate | {score.soic_pass_rate:.0%} |",
        f"| Coherence | {score.coherence:.0%} |",
        "",
    ]

    if score.coherence < 0.7:
        lines.append(
            "> **Note:** Low coherence indicates a significant gap between "
            "weighted scoring and gate-based evaluation."
        )
        lines.append("")

    return "\n".join(lines)
