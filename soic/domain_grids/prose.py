"""SOIC v3.0 — DOMAIN_PROSE: 5 quality gates for documentation files."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from . import register_domain
from ..models import GateResult, GateStatus


# Dossiers dont le contenu n'appartient pas a l'auteur du projet, ou qui sont
# regeneres. Sans cette exclusion, un TODO dans le README d'une dependance fait
# echouer la porte, et un projet Node se juge sur des milliers de fichiers tiers.
_DOSSIERS_EXCLUS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "site-packages",
        "vendor",
        "build",
        "dist",
        ".next",
        ".nuxt",
        "out",
        "target",
        "coverage",
        "htmlcov",
        ".cache",
    }
)


def _collect_files(
    path: str,
    extensions: tuple[str, ...] = (".md", ".rst", ".txt"),
) -> list[Path]:
    """Collect documentation files from a path, hors dossiers tiers ou generes."""
    p = Path(path)
    if p.is_file():
        return [p] if p.suffix in extensions else []
    files: list[Path] = []
    for ext in extensions:
        files.extend(
            f
            for f in p.rglob(f"*{ext}")
            if not (_DOSSIERS_EXCLUS & set(f.relative_to(p).parts[:-1]))
        )
    return sorted(files)


class UnreadableFileError(Exception):
    """Le fichier n'a pas pu etre lu : son contenu est inconnu, pas vide."""


def _read_text_safe(path: Path) -> str:
    """Read file text, raising when the content cannot be known.

    Historique : cette fonction retournait "" sur erreur d'encodage. Un fichier
    illisible etait alors traite comme un fichier vide, donc parfait, et passait
    P-01 a P-04 en PASS. Seule P-05 le voyait. Un contenu inconnu ne doit pas
    etre confondu avec un contenu sain.
    """
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        raise UnreadableFileError(str(path)) from exc


def _strip_code_blocks(content: str) -> str:
    """Retire les blocs de code delimites et indentes.

    Sans ca, un commentaire Python (`# ...`) dans un bloc de code se lit comme
    un titre markdown, et un placeholder cite en exemple compte comme un vrai.
    """
    content = re.sub(r"```[\s\S]*?```", "", content)
    content = re.sub(r"~~~[\s\S]*?~~~", "", content)
    content = re.sub(r"^(?: {4}|\t).*$", "", content, flags=re.MULTILINE)
    return content


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
            try:
                content = _read_text_safe(f)
            except UnreadableFileError:
                issues.append(f"{f.name} (illisible, contenu inconnu)")
                continue
            lines = content.splitlines()
            if len(lines) > 500:
                # Les titres sont cherches hors blocs de code : un commentaire
                # `# ...` dans un bloc n'est pas un titre markdown. Les deux
                # syntaxes comptent : ATX (`## Titre`) et setext (souligne par
                # ==== ou ----), sans quoi un document structure a l'ancienne
                # est declare sans aucun titre.
                propre = _strip_code_blocks(content)
                headings = re.findall(r"^#+\s", propre, re.MULTILINE)
                headings += re.findall(r"^(?!\s*$).+\n[=-]{3,}\s*$", propre, re.MULTILINE)
                # Un seul titre ne structure pas un fichier de plus de 500 lignes.
                # On exige au moins un titre par tranche de 250 lignes.
                attendu = max(1, len(lines) // 250)
                if len(headings) < attendu:
                    issues.append(
                        f"{f.name} ({len(lines)} lines, {len(headings)} heading(s), "
                        f"{attendu} attendu(s))"
                    )

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
    """P-02: Liens markdown vides, malformes, ou pointant vers un fichier absent.

    Portee assumee : cette porte verifie ce qui est verifiable sans reseau.
    Les liens locaux sont resolus sur le disque ; les URL externes ne sont pas
    appelees, donc leur cible n'est PAS validee. La porte ne pretend rien a
    leur sujet.
    """

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
            try:
                content = _read_text_safe(f)
            except UnreadableFileError:
                empty_links.append(f"{f.name}: illisible, contenu inconnu")
                continue
            for match in url_pattern.finditer(_strip_code_blocks(content)):
                link_text, url = match.group(1), match.group(2)
                url = url.strip()
                if not url:
                    empty_links.append(f"{f.name}: [{link_text}]()")
                elif url.startswith(("http://", "https://")):
                    if " " in url:
                        empty_links.append(f"{f.name}: URL malformee")
                    # Cible externe non appelee : hors de portee, rien n'est affirme.
                elif url.startswith(("#", "mailto:", "tel:", "/")):
                    # Ancre, protocole, ou chemin absolu de site : la racine du
                    # site publie est inconnue depuis le disque. Non resolvable,
                    # donc rien n'est affirme.
                    continue
                else:
                    # Lien local : resolvable, donc verifiable. Le chemin est
                    # decode au prealable — `mon%20image.png` designe un fichier
                    # dont le nom contient une espace.
                    chemin = unquote(url.split("#", 1)[0].split("?", 1)[0])
                    cible = (f.parent / chemin).resolve()
                    if not cible.exists():
                        empty_links.append(f"{f.name}: cible absente -> {url}")

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
            try:
                content = _read_text_safe(f)
            except UnreadableFileError:
                bad_files.append(f"{f.name} (illisible, contenu inconnu)")
                continue
            if len(content) < 100:
                continue
            # Les trois syntaxes de code : ``` , ~~~ , et l'indentation.
            code_blocks = re.findall(r"```[\s\S]*?```", content)
            code_blocks += re.findall(r"~~~[\s\S]*?~~~", content)
            sans_delimites = re.sub(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)", "", content)
            code_blocks += re.findall(r"^(?: {4}|\t).*$", sans_delimites, flags=re.MULTILINE)
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

    # Balises HTML inline courantes : `<span>` dans du markdown n'est pas un
    # emplacement a remplir. Sans cette exclusion, tout document melant HTML et
    # markdown declenche la porte.
    _HTML_INLINE: str = (
        r"span|strong|em|code|pre|div|p|br|hr|ul|ol|li|table|thead|tbody|tr|td|th"
        r"|a|img|b|i|u|s|sub|sup|small|mark|kbd|abbr|details|summary|figure"
        r"|figcaption|blockquote|section|article|header|footer|nav|main|aside|h[1-6]"
    )

    # Un placeholder est un emplacement laisse a remplir.
    _PLACEHOLDER_PATTERNS: tuple[str, ...] = (
        r"\[(?:TODO|PLACEHOLDER|TBD|FIXME|XXX|INSERT\b[^\]]*)\]",
        # [NOM DU PROJET], [A COMPLETER] : au moins deux mots en majuscules.
        # Un mot seul entre crochets est une etiquette courante ([CRITIQUE],
        # [MINEUR]) et ne designe pas un emplacement a remplir. Exclut aussi le
        # texte d'un lien `[GUIDE COMPLET](...)` et d'une reference `[VOIR][1]`.
        r"\[[A-ZÀ-Ý][A-ZÀ-Ý0-9,'’/\-]*(?: +[A-ZÀ-Ý0-9,'’/\-]+)+\](?![(\[])",
        # <remplir>, <PROJET> — mais pas une balise HTML ni une fermeture </...>.
        rf"<(?!/)(?!(?:{_HTML_INLINE})>)[a-zà-ÿA-ZÀ-Ý][a-zà-ÿA-ZÀ-Ý0-9 _\-]{{2,}}>",
        r"\bTBD\b",
        r"\bFIXME\b",
        r"(?<![\w`])TODO\b",
    )

    @staticmethod
    def _section_vide(contenu: str) -> str | None:
        """Rend le titre de la premiere section sans contenu, ou None.

        Une section est vide lorsqu'un titre est immediatement suivi d'un titre
        de niveau egal ou SUPERIEUR (moins de `#`), sans une ligne de texte entre
        les deux : la section annoncee n'a alors rien recu.

        `# Titre` suivi de `## Sous-titre` est au contraire une structure
        normale — le contenu viendra sous le sous-titre. Une expression
        reguliere seule ne distingue pas les deux : il faut comparer les niveaux.
        """
        titres = [
            (m.start(), len(m.group(1)), m.group(2).strip())
            for m in re.finditer(r"^(#{1,6}) +(\S.*)$", contenu, re.MULTILINE)
        ]
        for (debut, niveau, texte), (suivant_debut, niveau_suivant, _) in zip(
            titres, titres[1:], strict=False
        ):
            entre = contenu[contenu.index("\n", debut) + 1 : suivant_debut]
            if entre.strip():
                continue  # il y a du contenu, la section n'est pas vide
            if niveau_suivant <= niveau:
                return texte[:40]
        return None

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
            try:
                content = _read_text_safe(f)
            except UnreadableFileError:
                issues.append(f"{f.name} (illisible)")
                continue
            # Hors blocs de code : un placeholder montre en exemple dans un
            # extrait de code n'est pas un trou dans le document.
            propre = _strip_code_blocks(content)
            trouve = None
            for pat in self._PLACEHOLDER_PATTERNS:
                m = re.search(pat, propre, re.MULTILINE)
                if m:
                    trouve = m.group(0)[:24]
                    break
            if trouve is None:
                vide = self._section_vide(propre)
                if vide is not None:
                    trouve = f"section sans contenu : {vide}"
            if trouve is not None:
                issues.append(f"{f.name} ({trouve})")

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
