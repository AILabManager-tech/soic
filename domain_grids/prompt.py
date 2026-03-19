"""SOIC v3.0 — DOMAIN_PROMPT: 5 quality gates for prompt files."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from . import register_domain
from ..models import GateResult, GateStatus


def _collect_files(
    path: str, extensions: tuple[str, ...] = (".md", ".txt", ".prompt"),
) -> list[Path]:
    """Collect prompt-like files from a path."""
    p = Path(path)
    if p.is_file():
        return [p] if p.suffix in extensions else []
    files: list[Path] = []
    for ext in extensions:
        files.extend(p.rglob(f"*{ext}"))
    return sorted(files)


def _read_text_safe(path: Path) -> str:
    """Read file text, handling encoding errors."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


@dataclass
class UnresolvedVarsGate:
    """PR-01: Zero unresolved {{VAR}} template variables."""

    gate_id: str = "PR-01"
    name: str = "unresolved-vars"
    tool: str = "regex"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        files = _collect_files(path)
        if not files:
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.SKIP,
                evidence="No prompt files found", duration_ms=0, command="",
            )

        pattern = re.compile(r"\{\{[^}]*\}\}")
        findings: list[str] = []
        for f in files:
            content = _read_text_safe(f)
            matches = pattern.findall(content)
            if matches:
                findings.append(f"{f.name}: {', '.join(matches[:3])}")

        duration_ms = int((time.monotonic() - start) * 1000)
        if findings:
            evidence = f"{len(findings)} file(s) with unresolved vars: {'; '.join(findings[:5])}"
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.FAIL,
                evidence=evidence, duration_ms=duration_ms, command="regex scan {{VAR}}",
            )
        return GateResult(
            gate_id=self.gate_id, name=self.name, status=GateStatus.PASS,
            evidence="No unresolved template variables", duration_ms=duration_ms,
            command="regex scan {{VAR}}",
        )


@dataclass
class FallbackClausesGate:
    """PR-02: Fallback/uncertainty clauses present."""

    gate_id: str = "PR-02"
    name: str = "fallback-clauses"
    tool: str = "regex"

    _PATTERNS: tuple[str, ...] = (
        r"(?i)\bif\s+unsure\b",
        r"(?i)\bif\s+unclear\b",
        r"(?i)\bfallback\b",
        r"(?i)\botherwise\b",
        r"(?i)\bdefault\s*:",
        r"(?i)\bwhen\s+in\s+doubt\b",
        r"(?i)\bif\s+no\s+(?:information|data|context)\b",
    )

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        files = _collect_files(path)
        if not files:
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.SKIP,
                evidence="No prompt files found", duration_ms=0, command="",
            )

        files_with_fallback = 0
        for f in files:
            content = _read_text_safe(f)
            if any(re.search(p, content) for p in self._PATTERNS):
                files_with_fallback += 1

        duration_ms = int((time.monotonic() - start) * 1000)
        total = len(files)
        if files_with_fallback == 0 and total > 0:
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.FAIL,
                evidence=f"0/{total} files contain fallback clauses",
                duration_ms=duration_ms, command="regex scan fallback patterns",
            )
        return GateResult(
            gate_id=self.gate_id, name=self.name, status=GateStatus.PASS,
            evidence=f"{files_with_fallback}/{total} files contain fallback clauses",
            duration_ms=duration_ms, command="regex scan fallback patterns",
        )


@dataclass
class FormatConstraintGate:
    """PR-03: Constrained format verified (table/JSON/YAML blocks)."""

    gate_id: str = "PR-03"
    name: str = "format-constraint"
    tool: str = "regex"

    _FORMAT_PATTERNS: tuple[str, ...] = (
        r"```(?:json|yaml|yml|csv|xml|sql)",
        r"\|.*\|.*\|",  # table row
        r"(?i)format\s*:",
        r"(?i)output\s+format",
        r"(?i)respond\s+(?:in|with|using)\s+(?:json|yaml|table|csv)",
    )

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        files = _collect_files(path)
        if not files:
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.SKIP,
                evidence="No prompt files found", duration_ms=0, command="",
            )

        files_with_format = 0
        for f in files:
            content = _read_text_safe(f)
            if any(re.search(p, content) for p in self._FORMAT_PATTERNS):
                files_with_format += 1

        duration_ms = int((time.monotonic() - start) * 1000)
        total = len(files)
        if files_with_format == 0 and total > 0:
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.FAIL,
                evidence=f"0/{total} files specify output format constraints",
                duration_ms=duration_ms, command="regex scan format constraints",
            )
        return GateResult(
            gate_id=self.gate_id, name=self.name, status=GateStatus.PASS,
            evidence=f"{files_with_format}/{total} files specify output format",
            duration_ms=duration_ms, command="regex scan format constraints",
        )


@dataclass
class MarkdownStructureGate:
    """PR-04: Valid hierarchical Markdown structure."""

    gate_id: str = "PR-04"
    name: str = "md-structure"
    tool: str = "regex"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        files = _collect_files(path, extensions=(".md",))
        if not files:
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.SKIP,
                evidence="No Markdown files found", duration_ms=0, command="",
            )

        issues: list[str] = []
        for f in files:
            content = _read_text_safe(f)
            headings = re.findall(r"^(#+)\s", content, re.MULTILINE)
            if not headings:
                if len(content) > 200:
                    issues.append(f"{f.name}: no headings")
                continue
            levels = [len(h) for h in headings]
            # Check for skipped levels (e.g. # then ###)
            for i in range(1, len(levels)):
                if levels[i] > levels[i - 1] + 1:
                    issues.append(f"{f.name}: skipped heading level")
                    break

        duration_ms = int((time.monotonic() - start) * 1000)
        if issues:
            evidence = f"{len(issues)} issue(s): {'; '.join(issues[:5])}"
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.FAIL,
                evidence=evidence, duration_ms=duration_ms, command="heading structure check",
            )
        return GateResult(
            gate_id=self.gate_id, name=self.name, status=GateStatus.PASS,
            evidence="Valid heading hierarchy", duration_ms=duration_ms,
            command="heading structure check",
        )


@dataclass
class PlaceholderGate:
    """PR-05: Zero unresolved placeholders ([TODO], TBD, etc.)."""

    gate_id: str = "PR-05"
    name: str = "placeholders"
    tool: str = "regex"

    _PLACEHOLDER_PATTERNS: tuple[str, ...] = (
        r"\[TODO\]",
        r"\[PLACEHOLDER\]",
        r"\[INSERT\b",
        r"\[FILL\b",
        r"\bTBD\b",
        r"\bFIXME\b",
        r"\bXXX\b",
    )

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        files = _collect_files(path)
        if not files:
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.SKIP,
                evidence="No prompt files found", duration_ms=0, command="",
            )

        findings: list[str] = []
        for f in files:
            content = _read_text_safe(f)
            for pat in self._PLACEHOLDER_PATTERNS:
                matches = re.findall(pat, content)
                if matches:
                    findings.append(f"{f.name}: {matches[0]}")
                    break

        duration_ms = int((time.monotonic() - start) * 1000)
        if findings:
            evidence = (
                f"{len(findings)} file(s) with placeholders: {'; '.join(findings[:5])}"
            )
            return GateResult(
                gate_id=self.gate_id, name=self.name, status=GateStatus.FAIL,
                evidence=evidence, duration_ms=duration_ms, command="regex scan placeholders",
            )
        return GateResult(
            gate_id=self.gate_id, name=self.name, status=GateStatus.PASS,
            evidence="No unresolved placeholders", duration_ms=duration_ms,
            command="regex scan placeholders",
        )


def _load_prompt_gates() -> list:
    """Load all PROMPT domain gates."""
    return [
        UnresolvedVarsGate(),
        FallbackClausesGate(),
        FormatConstraintGate(),
        MarkdownStructureGate(),
        PlaceholderGate(),
    ]


register_domain("PROMPT", _load_prompt_gates)
