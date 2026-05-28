"""SOIC v3.0 — 9 Dimensions de qualite.

Chaque dimension est scoree de 0.0 a 10.0.
Used by PhaseGateReport.compute_score() and report.py.
"""

DIMENSIONS = {
    "D1": {
        "name": "Architecture",
        "description": "Modularite, separation des concerns, structure fichiers",
        "weight": 1.0,
    },
    "D2": {
        "name": "Documentation",
        "description": "README, CLAUDE.md, commentaires, JSDoc",
        "weight": 0.8,
    },
    "D3": {
        "name": "Tests",
        "description": "Couverture, qualite des assertions, edge cases",
        "weight": 0.9,
    },
    "D4": {
        "name": "Securite",
        "description": "Headers HTTP, XSS, CVE, CSRF, API keys",
        "weight": 1.2,
    },
    "D5": {
        "name": "Performance",
        "description": "Core Web Vitals, bundle size, cache, images",
        "weight": 1.0,
    },
    "D6": {
        "name": "Accessibilite",
        "description": "WCAG 2.2 AA, contraste, clavier, ARIA",
        "weight": 1.1,
    },
    "D7": {
        "name": "SEO",
        "description": "Meta, structured data, sitemap, robots",
        "weight": 1.0,
    },
    "D8": {
        "name": "Conformite legale",
        "description": "Loi 25, RGPD, mentions legales, cookies",
        "weight": 1.1,
    },
    "D9": {
        "name": "Code Quality",
        "description": "TypeScript strict, linting, conventions, DRY",
        "weight": 0.9,
        # NOTE: en ph0-discovery, D9 accepte des proxies de "qualité
        # distinctive" (ex: PE-09 competitive-gaps). Voir phase_early.py
        # CompetitiveGapsGate docstring + chantier mode B SESSION_04.5.
    },
}


def calculate_mu(scores: dict[str, float]) -> float:
    """Weighted average of the dimensions actually present in `scores`.

    Dimensions absent from `scores` are skipped from both numerator and
    denominator (they do not bias μ toward a neutral 5.0). Callers should use
    `coverage` as the separate signal for measurement completeness.
    """
    present = [dim for dim in scores if dim in DIMENSIONS]
    if not present:
        return 0.0
    total_weight = sum(DIMENSIONS[dim]["weight"] for dim in present)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(scores[dim] * DIMENSIONS[dim]["weight"] for dim in present)
    return weighted_sum / total_weight
