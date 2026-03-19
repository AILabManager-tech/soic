"""SOIC v3.0 — Feedback Router: corrective instructions for failed gates.

Consolidated: code-domain templates (C-01..C-06), web/phase templates (PE-*, W-*),
dimension priority system, and OSIRIS axis feedback.
"""

from __future__ import annotations

from .models import GateReport, GateResult, GateStatus, PhaseGateReport

# ── Dimension priorities (for phase-based sorting) ───────────────────────────

_DIM_PRIORITY: dict[str, int] = {
    "D4": 0,  # CRITIQUE -- Security
    "D8": 0,  # CRITIQUE -- Legal
    "D6": 1,  # HAUTE -- Accessibility
    "D5": 1,  # HAUTE -- Performance
    "D1": 2,  # NORMALE
    "D2": 2,
    "D3": 2,
    "D7": 2,
    "D9": 2,
}

_PRIORITY_LABELS = {0: "CRITIQUE", 1: "HAUTE", 2: "NORMALE"}

MAX_FEEDBACK_ITEMS = 5

# ── Code-domain corrective templates ─────────────────────────────────────────

_CODE_CORRECTIVE_TEMPLATES: dict[str, str] = {
    "C-01": (
        "**Linting (ruff):** Fix the reported lint violations.\n"
        "Run `ruff check {path} --statistics` to see details, "
        "then `ruff check {path} --fix` to auto-fix what's possible."
    ),
    "C-02": (
        "**Security (bandit):** Resolve HIGH/CRITICAL security issues.\n"
        "Run `bandit -r {path} -f json` and address each finding. "
        "Common fixes: avoid hardcoded passwords, use safe deserialization."
    ),
    "C-03": (
        "**Tests (pytest):** Fix failing tests.\n"
        "Run `python -m pytest {path} --tb=short -q -o \"addopts=\"` "
        "to identify failures. Fix broken assertions or missing fixtures."
    ),
    "C-04": (
        "**Complexity (radon):** Reduce cyclomatic complexity.\n"
        "Run `radon cc {path} -a -nc` to find complex functions (grade C+). "
        "Extract helper methods, simplify conditions, reduce nesting."
    ),
    "C-05": (
        "**Type checking (mypy):** Fix type errors.\n"
        "Run `mypy {path} --ignore-missing-imports` and resolve each error. "
        "Add type annotations and fix incompatible types."
    ),
    "C-06": (
        "**Secrets (gitleaks):** Remove detected secrets from source.\n"
        "Move secrets to environment variables or a .env file (gitignored). "
        "Rotate any exposed credentials immediately."
    ),
}

# ── Web/phase corrective templates (NEXOS) ───────────────────────────────────

_WEB_CORRECTIVE_TEMPLATES: dict[str, str] = {
    "PE-01": "Ajouter des sections ## claires, developper chaque section (min 500 chars, 3+ sections).",
    "PE-02": "Ajouter `Score global: X/10` ou `mu = X/10` dans une section ## Evaluation.",
    "PE-03": "Verifier que chaque section du template de phase est presente avec les titres standards.",
    "PE-04": "Remplacer CHAQUE [TODO], [TBD], [INSERT] par du contenu reel.",
    "W-01": "Verifier: app/ (ou src/app/), components/, tsconfig.json, package.json, next.config.mjs.",
    "W-02": "Ecrire README.md 200+ chars. Ajouter JSDoc aux composants principaux.",
    "W-03": "Executer `npx vitest run`, corriger assertions cassees et fixtures manquantes.",
    "W-04": "Executer `npx vitest run --coverage`, ajouter tests pour fichiers non couverts (cible >= 80%).",
    "W-05": "Executer `npm audit fix --force`. Verifier que le build passe apres correction.",
    "W-06": "Ajouter dans vercel.json: X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy, HSTS, CSP.",
    "W-07": "URGENT: Deplacer secrets vers variables server-side. Supprimer NEXT_PUBLIC_*KEY/*SECRET/*TOKEN.",
    "W-08": "Optimiser images (next/image, WebP), reduire JS non utilise (dynamic imports), verifier Core Web Vitals.",
    "W-09": "Utiliser `next/dynamic` pour code splitting. Eviter imports de librairies entieres.",
    "W-10": "Corriger erreurs pa11y: alt images, roles ARIA, contraste, navigation clavier (cible: 0 erreurs WCAG 2.2 AA).",
    "W-11": "Ajouter attributs ARIA manquants, verifier contraste (>= 4.5:1), accessibilite clavier.",
    "W-12": "Verifier meta tags (title, description, viewport, charset, lang). Liens avec texte descriptif.",
    "W-13": "Ajouter metadata dans layout.tsx (title, description, openGraph). Creer sitemap.ts et robots.ts.",
    "W-14": "OBLIGATOIRE: Page confidentialite, mentions legales, bandeau cookies opt-in, RPP identifie.",
    "W-15": "Executer `npx eslint . --fix`. Corriger erreurs restantes manuellement (cible: 0 erreurs).",
    "W-16": "Activer `strict: true` et `noUncheckedIndexedAccess: true` dans tsconfig.json. Eliminer `any`.",
    "W-17": "Aucun cookie non essentiel avant consentement. Verifier banniere opt-in et blocage scripts tiers.",
}

# Combined template lookup
_ALL_TEMPLATES: dict[str, str] = {**_CODE_CORRECTIVE_TEMPLATES, **_WEB_CORRECTIVE_TEMPLATES}


class FeedbackRouter:
    """Generates corrective feedback for failed gates.

    Works with both GateReport (domain/code) and PhaseGateReport (web/NEXOS).
    For PhaseGateReport: prioritizes by dimension and limits to top 5.
    For GateReport: includes all failures with code-specific templates.
    """

    def generate(self, report: GateReport | PhaseGateReport) -> str:
        """Produce a Markdown feedback block for failed gates.

        Dispatches to phase-based or domain-based formatting.
        """
        if isinstance(report, PhaseGateReport):
            return self._generate_phase(report)
        return self._generate_domain(report)

    def _generate_domain(self, report: GateReport) -> str:
        """Domain-based feedback (code gates C-01..C-06)."""
        failed_gates = [
            g for g in report.gates
            if g.status in (GateStatus.FAIL, GateStatus.ERROR)
        ]
        if not failed_gates:
            return "All gates passed. No corrective action needed."

        sections = [
            "## Corrective Feedback -- Iteration\n",
            f"**{len(failed_gates)} gate(s) require attention:**\n",
        ]
        for gate in failed_gates:
            template = _ALL_TEMPLATES.get(gate.gate_id, "Review and fix the reported issues.")
            instruction = template.format(path=report.target_path)
            sections.append(
                f"### {gate.gate_id} -- {gate.name} [{gate.status.value}]\n"
                f"**Evidence:** {gate.evidence}\n\n"
                f"{instruction}\n"
            )

        return "\n".join(sections)

    def _generate_phase(self, report: PhaseGateReport) -> str:
        """Phase-based feedback (web/NEXOS): top 5, prioritized by dimension."""
        failed_gates = [
            g for g in report.gates
            if g.status in (GateStatus.FAIL, GateStatus.ERROR)
        ]
        if not failed_gates:
            return "All gates passed. No corrective action needed."

        # Sort: priority (lower = more critical), then score (lower = worse)
        failed_gates.sort(key=lambda g: (_DIM_PRIORITY.get(g.dimension, 2), g.score))

        top = failed_gates[:MAX_FEEDBACK_ITEMS]
        deferred = len(failed_gates) - len(top)

        sections = [
            f"## Corrections requises (Iteration {report.iteration + 1})"
            f" -- {len(top)} prioritaires sur {len(failed_gates)} FAIL\n",
        ]

        for gate in top:
            priority = _PRIORITY_LABELS.get(_DIM_PRIORITY.get(gate.dimension, 2), "NORMALE")
            template = _ALL_TEMPLATES.get(gate.gate_id, "Review and fix the reported issues.")
            sections.append(
                f"[{gate.dimension}/{gate.gate_id}] {gate.name} -- {priority}\n"
                f"-> {gate.evidence}\n"
                f"-> Action : {template}\n"
            )

        if deferred > 0:
            sections.append(f"(+ {deferred} corrections mineures reportees)\n")

        return "\n".join(sections)

    def generate_full(self, report: PhaseGateReport) -> str:
        """Produce full feedback for ALL failed gates (for logging/reports)."""
        failed_gates = [
            g for g in report.gates
            if g.status in (GateStatus.FAIL, GateStatus.ERROR)
        ]
        if not failed_gates:
            return "All gates passed. No corrective action needed."

        failed_gates.sort(key=lambda g: (_DIM_PRIORITY.get(g.dimension, 2), g.score))

        sections = [
            f"## Full Corrective Feedback -- {report.phase} Iteration {report.iteration}\n",
            f"**{len(failed_gates)} gate(s) require attention** (mu={report.mu:.2f}):\n",
        ]

        for gate in failed_gates:
            priority = _PRIORITY_LABELS.get(_DIM_PRIORITY.get(gate.dimension, 2), "NORMALE")
            template = _ALL_TEMPLATES.get(gate.gate_id, "Review and fix the reported issues.")
            sections.append(
                f"### [{gate.dimension}/{gate.gate_id}] {gate.name} -- {priority} (score: {gate.score:.1f}/10)\n"
                f"**Evidence:** {gate.evidence}\n"
                f"**Action:** {template}\n"
            )

        return "\n".join(sections)


# ── Web-specific OSIRIS feedback templates ───────────────────────────────────

_WEB_FEEDBACK: dict[str, dict[str, str]] = {
    "O": {
        "low": (
            "**Performance critique.** Optimisez les Core Web Vitals : "
            "compressez images, minifiez JS/CSS, activez le lazy loading."
        ),
        "mid": (
            "**Performance acceptable.** Envisagez un CDN "
            "et le prechargement des ressources critiques."
        ),
    },
    "S": {
        "low": (
            "**Securite deficiente.** Ajoutez les headers manquants : "
            "HSTS, CSP, X-Frame-Options, Referrer-Policy."
        ),
        "mid": (
            "**Securite partielle.** Renforcez la CSP "
            "et activez Permissions-Policy."
        ),
    },
    "I": {
        "low": (
            "**Trop de trackers.** Reduisez les scripts tiers "
            "et utilisez un gestionnaire de consentement."
        ),
        "mid": (
            "**Quelques trackers presents.** "
            "Verifiez la conformite RGPD/CCPA."
        ),
    },
    "R": {
        "low": (
            "**Page trop lourde.** Compressez les assets, "
            "reduisez les requetes HTTP, optimisez les images."
        ),
        "mid": (
            "**Poids acceptable.** Utilisez des formats modernes "
            "(WebP, AVIF) et la compression Brotli."
        ),
    },
}


class WebFeedbackRouter:
    """Generates recommendations for underperforming OSIRIS axes."""

    def __init__(self, threshold: float = 7.0) -> None:
        self.threshold = threshold

    def generate(
        self,
        axes: dict[str, dict],
        weights: dict[str, float] | None = None,
        delta: dict[str, float] | None = None,
    ) -> list[dict[str, str]]:
        """Generate prioritized recommendations.

        Args:
            axes: Dict of axis_key -> {"score": float, ...}.
            weights: Optional weight per axis (for impact prioritization).
            delta: Optional delta per axis vs previous scan.

        Returns:
            List of {"axis": str, "priority": str, "recommendation": str}.
        """
        weights = weights or {"O": 0.20, "S": 0.30, "I": 0.30, "R": 0.20}
        recs: list[tuple[float, dict[str, str]]] = []

        for axis_key, data in axes.items():
            score = data.get("score", 10.0)
            if score >= self.threshold:
                continue

            level = "low" if score < 5.0 else "mid"
            feedback = _WEB_FEEDBACK.get(axis_key, {}).get(level, "")
            if not feedback:
                continue

            # Priority = weight * improvement potential
            w = weights.get(axis_key, 0.25)
            potential = self.threshold - score
            impact = w * potential

            delta_str = ""
            if delta and axis_key in delta:
                d = delta[axis_key]
                delta_str = f" (delta: {d:+.1f})"

            recs.append((impact, {
                "axis": axis_key,
                "priority": f"{impact:.2f}",
                "recommendation": feedback + delta_str,
            }))

        # Sort by impact descending
        recs.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in recs]
