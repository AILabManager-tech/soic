"""SOIC v3.0 — Classifier: auto-detect domain(s) from path content."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

_EXTENSION_MAP: dict[str, str] = {
    ".py": "CODE",
    ".js": "CODE",
    ".ts": "CODE",
    ".java": "CODE",
    ".go": "CODE",
    ".rs": "CODE",
    ".rb": "CODE",
    ".c": "CODE",
    ".cpp": "CODE",
    ".h": "CODE",
    ".md": "PROSE",
    ".rst": "PROSE",
    ".txt": "PROSE",
    ".yml": "INFRA",
    ".yaml": "INFRA",
    ".dockerfile": "INFRA",
    ".tf": "INFRA",
    ".hcl": "INFRA",
    ".toml": "INFRA",
}

_PROMPT_INDICATORS = (
    r"\{\{[^}]+\}\}",
    r"(?i)^ROLE\s*:",
    r"(?i)^DIRECTIVE\s*:",
    r"(?i)^SYSTEM\s*:",
    r"(?i)^USER\s*:",
    r"(?i)^ASSISTANT\s*:",
    r"(?i)\bprompt\b.*\btemplate\b",
)

_SKIP_DIRS = {
    "__pycache__", ".git", "node_modules", "venv", ".venv",
    "site-packages", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


def classify_domain(path: str) -> list[str]:
    """Classify path into one or more domains based on file extensions and content.

    Args:
        path: Path to a file or directory.

    Returns:
        List of detected domain names (e.g. ["CODE"], ["PROSE", "INFRA"]).
        Returns ["CODE"] as fallback if nothing detected.
    """
    p = Path(path)
    if p.is_file():
        return _classify_file(p)

    ext_counts: Counter[str] = Counter()
    has_dockerfile = False
    prompt_score = 0
    total_files = 0

    for f in p.rglob("*"):
        if not f.is_file():
            continue
        # Skip known non-project directories
        if any(skip in f.parts for skip in _SKIP_DIRS):
            continue

        total_files += 1

        # Check Dockerfile by name
        if f.name.startswith("Dockerfile") or f.name.endswith(".dockerfile"):
            has_dockerfile = True
            ext_counts["INFRA"] += 1
            continue

        domain = _EXTENSION_MAP.get(f.suffix.lower())
        if domain:
            ext_counts[domain] += 1

        # Sample for prompt indicators
        if f.suffix in (".md", ".txt", ".prompt") and prompt_score < 5:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")[:2000]
                if any(re.search(pat, content, re.MULTILINE) for pat in _PROMPT_INDICATORS):
                    prompt_score += 1
            except OSError:
                continue

    if total_files == 0:
        return ["CODE"]

    domains: list[str] = []
    total_classified = sum(ext_counts.values())

    if total_classified == 0:
        return ["CODE"]

    # A domain qualifies if it represents >= 30% of classified files
    threshold = max(1, total_classified * 0.3)
    for domain, count in ext_counts.most_common():
        if count >= threshold:
            domains.append(domain)

    # Add INFRA if Dockerfiles detected even below threshold
    if has_dockerfile and "INFRA" not in domains:
        domains.append("INFRA")

    # Add PROMPT if enough indicators found
    if prompt_score >= 2 and "PROMPT" not in domains:
        domains.append("PROMPT")

    return domains if domains else ["CODE"]


def _classify_file(path: Path) -> list[str]:
    """Classify a single file."""
    if path.name.startswith("Dockerfile") or path.name.endswith(".dockerfile"):
        return ["INFRA"]

    domain = _EXTENSION_MAP.get(path.suffix.lower())
    if not domain:
        return ["CODE"]

    domains = [domain]

    # Check for prompt content in text files
    if path.suffix in (".md", ".txt", ".prompt"):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")[:2000]
            has_prompt = any(
                re.search(pat, content, re.MULTILINE) for pat in _PROMPT_INDICATORS
            )
            if has_prompt and "PROMPT" not in domains:
                domains.append("PROMPT")
        except OSError:
            pass

    return domains
