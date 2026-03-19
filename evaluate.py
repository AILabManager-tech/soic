"""SOIC v3.0 — Evaluation objective (tool-verified).

NOTE: evaluate_d8_legal() is the primary export, reused by W-14 gate.
evaluate_from_tooling() and evaluate_all() are DEPRECATED -- use GateEngine instead.
"""

import json
import subprocess
import warnings
from pathlib import Path

from .dimensions import calculate_mu


def evaluate_d8_legal(client_dir: Path) -> float:
    """Evalue D8 Conformite legale en scannant le code source du site.

    Retourne un score sur 10.0 base sur 6 verifications programmatiques.
    Score 0.0 si aucun element de conformite n'est trouve.
    """
    site_dir = client_dir / "site"
    if not site_dir.exists():
        return 0.0

    score = 0.0
    total = 6

    # 1. Politique de confidentialite
    privacy_files = (
        list(site_dir.rglob("*confidentialit*"))
        + list(site_dir.rglob("*privacy*"))
        + list(site_dir.rglob("*politique*"))
    )
    privacy_files = [f for f in privacy_files
                     if "node_modules" not in str(f) and ".next" not in str(f)]
    if privacy_files:
        score += 1

    # 2. Mentions legales
    legal_files = (
        list(site_dir.rglob("*mention*legal*"))
        + list(site_dir.rglob("*legal*"))
    )
    legal_files = [f for f in legal_files
                   if "node_modules" not in str(f) and ".next" not in str(f)]
    if legal_files:
        score += 1

    # 3. Bandeau cookies / consentement
    try:
        grep_result = subprocess.run(
            ["grep", "-rl", "-i",
             r"cookie.*consent\|consentement\|cookie.*banner",
             str(site_dir / "src") if (site_dir / "src").exists() else str(site_dir)],
            capture_output=True, text=True, timeout=10,
        )
        if grep_result.stdout.strip():
            score += 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 4. vercel.json avec headers secu
    vercel_json = site_dir / "vercel.json"
    if vercel_json.exists():
        try:
            content = vercel_json.read_text().lower()
            required_headers = [
                "x-content-type-options", "x-frame-options",
                "referrer-policy", "strict-transport-security",
            ]
            headers_found = sum(1 for h in required_headers if h in content)
            score += headers_found / len(required_headers)
        except Exception:
            pass

    # 5. Pas de cles API cote client
    search_dir = str(site_dir / "src") if (site_dir / "src").exists() else str(site_dir)
    try:
        grep_api = subprocess.run(
            ["grep", "-rl",
             r"NEXT_PUBLIC.*KEY\|NEXT_PUBLIC.*SECRET\|NEXT_PUBLIC.*TOKEN",
             search_dir],
            capture_output=True, text=True, timeout=10,
        )
        if not grep_api.stdout.strip():
            score += 1  # Pas de fuite = bon
    except (subprocess.TimeoutExpired, FileNotFoundError):
        score += 1  # Impossible de verifier = presumer OK

    # 6. RPP identifie quelque part
    try:
        grep_rpp = subprocess.run(
            ["grep", "-rl", "-i",
             r"responsable.*protection\|privacy.*officer\|RPP",
             search_dir],
            capture_output=True, text=True, timeout=10,
        )
        if grep_rpp.stdout.strip():
            score += 1
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return round((score / total) * 10.0, 1)


def evaluate_from_tooling(tooling_dir: Path) -> dict[str, float]:
    """Calcule les scores a partir des mesures reelles des outils CLI.

    DEPRECATED: Use GateEngine with domain_grids/web.py gates instead.
    """
    warnings.warn(
        "evaluate_from_tooling() is deprecated. Use GateEngine.run_all_gates() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    scores: dict[str, float] = {}

    # D5 Performance -- Lighthouse reel
    lh_path = tooling_dir / "lighthouse.json"
    if lh_path.exists():
        try:
            lh = json.loads(lh_path.read_text())
            perf = lh.get("categories", {}).get("performance", {}).get("score", 0)
            scores["D5"] = perf * 10
        except (json.JSONDecodeError, KeyError):
            scores["D5"] = 5.0
    else:
        scores["D5"] = 5.0

    # D6 Accessibilite -- pa11y reel
    pa11y_path = tooling_dir / "pa11y.json"
    if pa11y_path.exists():
        try:
            pa11y = json.loads(pa11y_path.read_text())
            if isinstance(pa11y, list):
                errors = len([i for i in pa11y if i.get("type") == "error"])
            else:
                errors = pa11y.get("total", 0)
            scores["D6"] = max(0.0, 10.0 - errors * 0.5)
        except (json.JSONDecodeError, KeyError):
            scores["D6"] = 5.0
    else:
        scores["D6"] = 5.0

    # D4 Securite -- Headers HTTP reels
    headers_path = tooling_dir / "headers.json"
    if headers_path.exists():
        try:
            headers = json.loads(headers_path.read_text())
            header_names = {k.lower() for k in headers.keys()}
            required = [
                "x-content-type-options", "x-frame-options",
                "referrer-policy", "permissions-policy",
                "strict-transport-security", "content-security-policy",
            ]
            present = sum(1 for h in required if h in header_names)
            score_headers = (present / len(required)) * 10
        except (json.JSONDecodeError, KeyError):
            score_headers = 5.0
    else:
        score_headers = 5.0

    # D4 Securite -- npm audit reel
    audit_path = tooling_dir / "npm-audit.json"
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text())
            vulns = audit.get("metadata", {}).get("vulnerabilities", {})
            high = vulns.get("high", 0) + vulns.get("critical", 0)
            score_deps = max(0.0, 10.0 - high * 2)
        except (json.JSONDecodeError, KeyError):
            score_deps = 5.0
    else:
        score_deps = 5.0

    scores["D4"] = (score_headers + score_deps) / 2

    # D7 SEO -- Lighthouse SEO
    if lh_path.exists():
        try:
            lh = json.loads(lh_path.read_text())
            seo = lh.get("categories", {}).get("seo", {}).get("score", 0)
            scores["D7"] = seo * 10
        except (json.JSONDecodeError, KeyError):
            scores["D7"] = 5.0
    else:
        scores["D7"] = 5.0

    # D6 Accessibilite -- Lighthouse a11y (complement pa11y)
    if lh_path.exists():
        try:
            lh = json.loads(lh_path.read_text())
            a11y_lh = lh.get("categories", {}).get("accessibility", {}).get("score", 0)
            scores["D6"] = (scores["D6"] + a11y_lh * 10) / 2
        except (json.JSONDecodeError, KeyError):
            pass

    # D8 Conformite legale -- Evaluation programmatique
    client_dir = tooling_dir.parent
    d8_score = evaluate_d8_legal(client_dir)
    scores["D8"] = d8_score

    # Dimensions sans tooling (evaluees par les agents LLM)
    for dim in ["D1", "D2", "D3", "D9"]:
        if dim not in scores:
            scores[dim] = 5.0

    return scores


def evaluate_all(tooling_dir: Path) -> tuple[dict[str, float], float]:
    """Evalue toutes les dimensions et calcule mu.

    DEPRECATED: Use GateEngine.run_all_gates() instead.
    """
    warnings.warn(
        "evaluate_all() is deprecated. Use GateEngine.run_all_gates() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    scores = evaluate_from_tooling(tooling_dir)
    mu = calculate_mu(scores)
    return scores, mu
