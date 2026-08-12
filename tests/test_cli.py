"""Tests for soic.cli."""

import subprocess
import sys


class TestCliEntryPoint:
    def test_module_imports(self):
        # Le renommage soic_v3 -> soic (3cc27ab) avait laissé 4 imports
        # `soic_v3.domain_grids.*` ici : le point d'entrée déclaré dans
        # pyproject (`soic = soic.cli:main`) levait ImportError. Aucun test
        # n'importait la CLI, donc rien ne l'a signalé.
        import soic.cli

        assert callable(soic.cli.main)

    def test_domain_grids_are_registered_on_import(self):
        import soic.cli  # noqa: F401
        from soic.domain_grids import list_domains

        registered = list_domains()
        for expected in ("CODE", "INFRA", "PROMPT", "PROSE"):
            assert expected in registered

    def test_runs_as_module(self):
        result = subprocess.run(
            [sys.executable, "-m", "soic", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
