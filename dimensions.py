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
    },
}


def calculate_mu(scores: dict[str, float]) -> float:
    """Calcule mu = moyenne ponderee des dimensions."""
    total_weight = sum(d["weight"] for d in DIMENSIONS.values())
    weighted_sum = sum(
        scores.get(dim, 0.0) * DIMENSIONS[dim]["weight"]
        for dim in DIMENSIONS
    )
    return weighted_sum / total_weight
