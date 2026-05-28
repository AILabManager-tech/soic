"""SOIC v3.0 — DOMAIN_PROSE: 5 quality gates for documentation files."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from . import register_domain
from ..models import GateResult, GateStatus


def _collect_files(
    path: str,
    extensions: tuple[str, ...] = (".md", ".rst", ".txt"),
) -> list[Path]:
    """Collect documentation files from a path."""
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
class HeadingsGate:
    """P-01: Files > 500 lines must have headings."""

    gate_id: str = "P-01"
    name: str = "headings"
    tool: str = "regex"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        files = _collect_files(path)
        if not files:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence="No documentation files found",
                duration_ms=0,
                command="",
            )

        issues: list[str] = []
        for f in files:
            content = _read_text_safe(f)
            lines = content.splitlines()
            if len(lines) > 500:
                headings = re.findall(r"^#+\s", content, re.MULTILINE)
                if not headings:
                    issues.append(f"{f.name} ({len(lines)} lines, no headings)")

        duration_ms = int((time.monotonic() - start) * 1000)
        if issues:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=(f"{len(issues)} long file(s) without headings: {'; '.join(issues[:3])}"),
                duration_ms=duration_ms,
                command="heading check",
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence="All long files have headings",
            duration_ms=duration_ms,
            command="heading check",
        )


@dataclass
class BrokenLinksGate:
    """P-02: Detect broken URLs via regex check."""

    gate_id: str = "P-02"
    name: str = "broken-links"
    tool: str = "regex"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        files = _collect_files(path)
        if not files:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence="No documentation files found",
                duration_ms=0,
                command="",
            )

        empty_links: list[str] = []
        url_pattern = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
        for f in files:
            content = _read_text_safe(f)
            for match in url_pattern.finditer(content):
                link_text, url = match.group(1), match.group(2)
                # Check for obviously broken links
                if not url or url.isspace():
                    empty_links.append(f"{f.name}: [{link_text}]()")
                elif url.startswith(("http://", "https://")) and " " in url:
                    empty_links.append(f"{f.name}: malformed URL")

        duration_ms = int((time.monotonic() - start) * 1000)
        if empty_links:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=(f"{len(empty_links)} broken link(s): {'; '.join(empty_links[:3])}"),
                duration_ms=duration_ms,
                command="link check",
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence="No obviously broken links",
            duration_ms=duration_ms,
            command="link check",
        )


@dataclass
class CodeTextRatioGate:
    """P-03: Reasonable code-blocks to text ratio."""

    gate_id: str = "P-03"
    name: str = "code-ratio"
    tool: str = "regex"

    _MAX_CODE_RATIO: float = 0.8

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        files = _collect_files(path)
        if not files:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence="No documentation files found",
                duration_ms=0,
                command="",
            )

        bad_files: list[str] = []
        for f in files:
            content = _read_text_safe(f)
            if len(content) < 100:
                continue
            code_blocks = re.findall(r"```[\s\S]*?```", content)
            code_chars = sum(len(b) for b in code_blocks)
            total_chars = len(content)
            if total_chars > 0 and code_chars / total_chars > self._MAX_CODE_RATIO:
                ratio = code_chars / total_chars
                bad_files.append(f"{f.name} ({ratio:.0%} code)")

        duration_ms = int((time.monotonic() - start) * 1000)
        if bad_files:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=(
                    f"{len(bad_files)} file(s) excessive code ratio: {'; '.join(bad_files[:3])}"
                ),
                duration_ms=duration_ms,
                command="code ratio check",
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence="Code-to-text ratio acceptable",
            duration_ms=duration_ms,
            command="code ratio check",
        )


@dataclass
class EmptySectionsGate:
    """P-04: Zero empty sections or placeholders."""

    gate_id: str = "P-04"
    name: str = "empty-sections"
    tool: str = "regex"

    _PLACEHOLDER_PATTERNS: tuple[str, ...] = (
        r"\[TODO\]",
        r"\[PLACEHOLDER\]",
        r"\[INSERT\b",
        r"\bTBD\b",
        r"\bFIXME\b",
        r"^\s*#+ .+\n\s*\n\s*#+ ",  # heading followed by empty then heading
    )

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        files = _collect_files(path)
        if not files:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence="No documentation files found",
                duration_ms=0,
                command="",
            )

        issues: list[str] = []
        for f in files:
            content = _read_text_safe(f)
            for pat in self._PLACEHOLDER_PATTERNS:
                if re.search(pat, content, re.MULTILINE):
                    issues.append(f.name)
                    break

        duration_ms = int((time.monotonic() - start) * 1000)
        if issues:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=(
                    f"{len(issues)} file(s) with empty sections/placeholders: "
                    f"{'; '.join(issues[:5])}"
                ),
                duration_ms=duration_ms,
                command="placeholder check",
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence="No empty sections or placeholders",
            duration_ms=duration_ms,
            command="placeholder check",
        )


@dataclass
class Utf8EncodingGate:
    """P-05: Clean UTF-8 encoding."""

    gate_id: str = "P-05"
    name: str = "utf8-encoding"
    tool: str = "python"

    def run(self, path: str, test_path: str | None = None) -> GateResult:
        start = time.monotonic()
        p = Path(path)
        if p.is_file():
            all_files = [p]
        else:
            all_files = sorted(
                f for f in p.rglob("*") if f.is_file() and f.suffix in (".md", ".rst", ".txt")
            )

        if not all_files:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.SKIP,
                evidence="No documentation files found",
                duration_ms=0,
                command="",
            )

        bad_files: list[str] = []
        for f in all_files:
            try:
                f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                bad_files.append(f.name)
            except OSError:
                continue

        duration_ms = int((time.monotonic() - start) * 1000)
        if bad_files:
            return GateResult(
                gate_id=self.gate_id,
                name=self.name,
                status=GateStatus.FAIL,
                evidence=(f"{len(bad_files)} file(s) not valid UTF-8: {', '.join(bad_files[:5])}"),
                duration_ms=duration_ms,
                command="utf-8 check",
            )
        return GateResult(
            gate_id=self.gate_id,
            name=self.name,
            status=GateStatus.PASS,
            evidence=f"{len(all_files)} file(s) valid UTF-8",
            duration_ms=duration_ms,
            command="utf-8 check",
        )


def _load_prose_gates() -> list:
    """Load all PROSE domain gates."""
    return [
        HeadingsGate(),
        BrokenLinksGate(),
        CodeTextRatioGate(),
        EmptySectionsGate(),
        Utf8EncodingGate(),
    ]


register_domain("PROSE", _load_prose_gates)
