"""Stub — HexaBrief knowledge scoring not yet implemented in soic_v3.

Ce module est référencé par orchestrator.py (l1398, l1477) pour le mode
HexaBrief scoring, mais n'est présent dans aucune source retrouvée.

Ce stub empêche l'ImportError au boot du CLI. L'appel effectif aux
fonctions lève NotImplementedError pour signaler clairement l'indisponibilité
du mode HexaBrief jusqu'à implémentation ou port depuis une source externe.

TODO(chantier2): implémenter, porter depuis une source, ou retirer les
code paths qui l'invoquent dans orchestrator.py.
"""
from __future__ import annotations

from typing import Any


def score_knowledge(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(
        "soic.knowledge_scoring: mode HexaBrief désactivé. "
        "Voir chantier2 suite phase A (module absent dans soic_v3)."
    )


__all__ = ["score_knowledge"]
