"""Tests for soic.domain_grids.prose.

Chaque porte porte deux tests, et c'est le second qui compte :

- un cas SAIN, qui doit rendre PASS — il verifie que la porte ne bloque pas tout ;
- un CONTRE-EXEMPLE, qui doit rendre FAIL — il verifie que la porte n'est pas aveugle.

Un cas sain seul ne prouve rien : une porte qui repondrait PASS a tout le passerait
aussi. Les contre-exemples ci-dessous sont ceux qui ont fait tomber P-01, P-02, P-03
et P-04 lors de l'essai du 2026-08-16.
"""

import pytest

from soic.domain_grids.prose import (
    BrokenLinksGate,
    CodeTextRatioGate,
    EmptySectionsGate,
    HeadingsGate,
    Utf8EncodingGate,
    _collect_files,
)
from soic.models import GateStatus


@pytest.fixture
def doc(tmp_path):
    """Ecrit un fichier markdown dans un dossier temporaire, rend le dossier."""

    def _write(nom, contenu, binaire=None):
        p = tmp_path / nom
        if binaire is not None:
            p.write_bytes(binaire)
        else:
            p.write_text(contenu, encoding="utf-8")
        return tmp_path

    return _write


def _long_corps(n=600, prefixe="Phrase"):
    return "\n".join(f"{prefixe} {i} de prose ordinaire." for i in range(n))


class TestHeadingsGate:
    def test_pass_fichier_structure(self, doc):
        corps = "\n\n".join(f"## Section {i}\n\n" + _long_corps(90) for i in range(6))
        d = doc("guide.md", "# Guide\n\n" + corps)
        assert HeadingsGate().run(str(d)).status == GateStatus.PASS

    def test_fail_commentaire_de_code_pris_pour_un_titre(self, doc):
        """Contre-exemple : aucun titre, seul un `#` a l'interieur d'un bloc de code.

        Avant correction, `re.findall(r"^#+\\s")` sur le contenu brut voyait le
        commentaire Python et rendait PASS sur un fichier sans aucune structure.
        """
        d = doc(
            "long.md",
            _long_corps(600) + "\n\n```python\n# pas un titre, un commentaire\nx = 1\n```\n",
        )
        assert HeadingsGate().run(str(d)).status == GateStatus.FAIL

    def test_fail_un_seul_titre_pour_un_tres_long_fichier(self, doc):
        """Un titre unique ne structure pas 600 lignes : il en faut un par 250."""
        d = doc("long.md", "# Titre unique\n\n" + _long_corps(600))
        assert HeadingsGate().run(str(d)).status == GateStatus.FAIL

    def test_pass_titres_setext(self, doc):
        """Les titres soulignes par ==== ou ---- comptent aussi.

        `^#+\\s` seul declarait « 0 heading » sur un document parfaitement
        structure a l'ancienne.
        """
        d = doc(
            "doc.md",
            "Guide complet\n=============\n\n"
            + _long_corps(200)
            + "\n\nPremiere partie\n---------------\n\n"
            + _long_corps(200)
            + "\n\nSeconde partie\n--------------\n\n"
            + _long_corps(200),
        )
        assert HeadingsGate().run(str(d)).status == GateStatus.PASS


class TestBrokenLinksGate:
    def test_pass_liens_valides(self, doc):
        d = doc("cible.md", "# Cible\n\ncontenu\n")
        (d / "index.md").write_text(
            "# Index\n\n[cible](./cible.md) · [externe](https://example.com) · [ancre](#index)\n",
            encoding="utf-8",
        )
        assert BrokenLinksGate().run(str(d)).status == GateStatus.PASS

    def test_fail_lien_local_vers_fichier_absent(self, doc):
        """Contre-exemple : avant correction, seuls `[x]()` et les URL a espace
        etaient vus. Un lien local vers un fichier inexistant passait."""
        d = doc("index.md", "# Index\n\nVoir le [guide](./absent.md).\n")
        assert BrokenLinksGate().run(str(d)).status == GateStatus.FAIL

    def test_pass_url_externe_non_appelee(self, doc):
        """Portee assumee : la porte ne fait pas de reseau, donc elle n'affirme
        rien sur une cible externe — meme invraisemblable."""
        d = doc("index.md", "# Index\n\n[site](https://domaine-inexistant-zzz.invalid)\n")
        assert BrokenLinksGate().run(str(d)).status == GateStatus.PASS

    def test_pass_chemin_encode(self, doc):
        """`mon%20image.png` designe un fichier dont le nom contient une espace :
        le chemin doit etre decode avant d'etre resolu."""
        d = doc("doc.md", "# Doc\n\n![vue](./mon%20image.png)\n")
        (d / "mon image.png").write_bytes(b"x")
        assert BrokenLinksGate().run(str(d)).status == GateStatus.PASS

    def test_pass_chemin_absolu_de_site(self, doc):
        """Faux positif introduit le 2026-08-16, puis corrige : `/docs/x.md` est
        un chemin relatif a la racine du site publie, pas au disque. La racine
        etant inconnue ici, le lien n'est pas resolvable et rien n'est affirme."""
        d = doc("index.md", "# Index\n\nVoir [la doc](/docs/reference.md).\n")
        assert BrokenLinksGate().run(str(d)).status == GateStatus.PASS


class TestCodeTextRatioGate:
    def test_pass_ratio_raisonnable(self, doc):
        d = doc("guide.md", "# Guide\n\n" + _long_corps(120) + "\n\n```py\nx = 1\n```\n")
        assert CodeTextRatioGate().run(str(d)).status == GateStatus.PASS

    def test_fail_code_indente_sans_backticks(self, doc):
        """Contre-exemple : avant correction, seuls les blocs ``` etaient comptes.
        Un fichier fait uniquement de code indente affichait 0 % de code."""
        code = "\n".join(f"    ligne_{i} = compute({i})" for i in range(200))
        d = doc("toutcode.md", "Doc.\n\n" + code + "\n")
        assert CodeTextRatioGate().run(str(d)).status == GateStatus.FAIL


class TestEmptySectionsGate:
    def test_pass_titre_suivi_de_sous_titre(self, doc):
        """Non-regression : `# Titre` suivi de `## Sous-titre` est une structure
        markdown normale. Avant correction, ce motif marquait 12 fichiers sur 12
        comme porteurs d'une section vide."""
        d = doc("doc.md", "# Rapport\n\n## Contexte\n\nDu contenu reel ici.\n")
        assert EmptySectionsGate().run(str(d)).status == GateStatus.PASS

    def test_fail_placeholder_de_gabarit(self, doc):
        """Contre-exemple : `[NOM DU PROJET]` n'etait dans aucun motif."""
        d = doc("doc.md", "# Rapport\n\n## Client\n\nLe client est [NOM DU PROJET].\n")
        assert EmptySectionsGate().run(str(d)).status == GateStatus.FAIL

    def test_fail_chevrons_et_todo_nu(self, doc):
        d = doc("doc.md", "# Rapport\n\n## Date\n\nLivraison : <remplir>.\n\nTODO revoir.\n")
        assert EmptySectionsGate().run(str(d)).status == GateStatus.FAIL

    def test_fail_section_reellement_vide(self, doc):
        """Deux titres de meme niveau sans une ligne de contenu entre eux."""
        d = doc("doc.md", "# Doc\n\n## Contexte\n\n## Budget\n\nDu contenu.\n")
        assert EmptySectionsGate().run(str(d)).status == GateStatus.FAIL

    def test_fail_section_vide_suivie_dun_niveau_superieur(self, doc):
        """`## Vide` suivi de `# Autre` : la sous-section n'a rien recu non plus.

        L'ancienne expression reguliere exigeait le meme niveau via un
        backreference et manquait ce cas.
        """
        d = doc("doc.md", "# Doc\n\n## Vide\n\n# Autre chapitre\n\nDu contenu.\n")
        assert EmptySectionsGate().run(str(d)).status == GateStatus.FAIL

    def test_pass_etiquette_en_majuscules(self, doc):
        """`[CRITIQUE]` est une etiquette de severite, pas un emplacement a
        remplir. Un placeholder de gabarit compte au moins deux mots."""
        d = doc(
            "doc.md",
            "# Rapport\n\n## Constats\n\n| Item | Gravite |\n|---|---|\n"
            "| Fuite | [CRITIQUE] |\n| Lenteur | [MINEUR] |\n",
        )
        assert EmptySectionsGate().run(str(d)).status == GateStatus.PASS

    def test_pass_cases_a_cocher(self, doc):
        d = doc("doc.md", "# Liste\n\n## Taches\n\n- [ ] a faire\n- [x] fait\n")
        assert EmptySectionsGate().run(str(d)).status == GateStatus.PASS

    def test_pass_placeholder_montre_en_exemple(self, doc):
        """Un placeholder cite dans un bloc de code est une illustration, pas un trou."""
        d = doc("doc.md", "# Doc\n\n## Usage\n\n```\nremplacer [NOM DU PROJET]\n```\n\nFin.\n")
        assert EmptySectionsGate().run(str(d)).status == GateStatus.PASS

    # -- Faux positifs introduits par la correction du 2026-08-16, puis corriges.
    #    Ces trois cas sont du markdown legitime : la porte doit se taire.

    def test_pass_lien_dont_le_texte_est_en_majuscules(self, doc):
        """`[GUIDE COMPLET](...)` est un lien, pas un emplacement a remplir."""
        d = doc("cible.md", "# Cible\n\ncontenu\n")
        (d / "doc.md").write_text(
            "# Doc\n\n## Reference\n\nVoir le [GUIDE COMPLET](./cible.md).\n", encoding="utf-8"
        )
        assert EmptySectionsGate().run(str(d)).status == GateStatus.PASS

    def test_pass_html_inline(self, doc):
        """`<span>` dans du markdown est une balise, pas un placeholder."""
        d = doc("doc.md", "# Doc\n\n## Note\n\nCeci est <span>important</span> et <em>net</em>.\n")
        assert EmptySectionsGate().run(str(d)).status == GateStatus.PASS

    def test_pass_points_de_suspension(self, doc):
        """Une phrase qui s'acheve sur des points de suspension reste de la prose."""
        d = doc("doc.md", "# Doc\n\n## Contexte\n\nCa fonctionnait, puis plus rien...\n")
        assert EmptySectionsGate().run(str(d)).status == GateStatus.PASS


class TestUtf8EncodingGate:
    def test_pass_utf8(self, doc):
        d = doc("doc.md", "# Procédé\n\nVérification terminée.\n")
        assert Utf8EncodingGate().run(str(d)).status == GateStatus.PASS

    def test_fail_latin1(self, doc):
        d = doc("doc.md", "", binaire="# Proc\xe9d\xe9\n".encode("latin-1"))
        assert Utf8EncodingGate().run(str(d)).status == GateStatus.FAIL


class TestPerimetreDeCollecte:
    """Les portes ne jugent pas le code des autres.

    `rglob` ramassait `node_modules`, `.git`, `.venv`, `build`… Un TODO dans le
    README d'une dependance faisait echouer la porte, et un projet Node se
    jugeait sur des milliers de fichiers tiers.
    """

    def test_dossiers_tiers_et_generes_ignores(self, doc):
        d = doc("README.md", "# Projet\n\n## Etat\n\nPropre.\n")
        for sous in ("node_modules/paquet", ".git", ".venv/lib", "build", "dist"):
            (d / sous).mkdir(parents=True, exist_ok=True)
            (d / sous / "README.md").write_text("# Tiers\n\nTODO externe.\n", encoding="utf-8")
        assert [f.name for f in _collect_files(str(d))] == ["README.md"]
        assert EmptySectionsGate().run(str(d)).status == GateStatus.PASS


class TestFichierIllisible:
    """Un fichier au contenu inconnu ne doit pas etre traite comme un fichier sain.

    Avant correction, `_read_text_safe` rendait "" sur erreur d'encodage : les
    quatre portes ci-dessous voyaient un fichier vide, donc parfait, et rendaient
    PASS. Seule P-05 voyait le probleme — un fichier corrompu obtenait 4 PASS sur 5.
    """

    @pytest.mark.parametrize(
        "gate_cls",
        [HeadingsGate, BrokenLinksGate, CodeTextRatioGate, EmptySectionsGate],
    )
    def test_fail_au_lieu_de_pass_silencieux(self, doc, gate_cls):
        d = doc("doc.md", "", binaire="# Proc\xe9d\xe9\n".encode("latin-1"))
        assert gate_cls().run(str(d)).status == GateStatus.FAIL
