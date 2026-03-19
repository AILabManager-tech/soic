"""SOIC v3.0 — Domain grid registry.

Consolidated: supports both domain-based and phase-based gate selection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# ── Domain-based registry (code quality) ─────────────────────────────────────

_DOMAIN_REGISTRY: dict[str, Callable] = {}


def register_domain(name: str, loader: Callable) -> None:
    """Register a domain grid loader function."""
    _DOMAIN_REGISTRY[name.upper()] = loader


def get_domain_gates(domain: str) -> list:
    """Return gate instances for the given domain."""
    loader = _DOMAIN_REGISTRY.get(domain.upper())
    if loader is None:
        raise ValueError(f"Unknown domain: {domain!r}. Available: {list(_DOMAIN_REGISTRY)}")
    return loader()


def list_domains() -> list[str]:
    """Return list of registered domain names."""
    return list(_DOMAIN_REGISTRY)


# ── Phase-based registry (NEXOS web pipeline) ───────────────────────────────

_GATE_SET_REGISTRY: dict[str, Callable] = {}

_PHASE_GATE_MAP: dict[str, str] = {
    "ph0-discovery": "PHASE_EARLY",
    "ph1-strategy": "PHASE_EARLY",
    "ph2-design": "PHASE_EARLY",
    "ph3-content": "PHASE_EARLY",
    "ph4-build": "WEB_BUILD",
    "ph5-qa": "WEB_FULL",
}


def register_gate_set(name: str, loader_fn: Callable) -> None:
    """Register a named gate set loader (phase-based)."""
    _GATE_SET_REGISTRY[name.upper()] = loader_fn


def get_phase_gates(phase: str) -> list:
    """Return gate instances for the given NEXOS phase."""
    gate_set_name = _PHASE_GATE_MAP.get(phase)
    if gate_set_name is None:
        raise ValueError(f"Unknown phase: {phase!r}. Available: {list(_PHASE_GATE_MAP)}")
    loader = _GATE_SET_REGISTRY.get(gate_set_name)
    if loader is None:
        raise ValueError(f"Gate set {gate_set_name!r} not registered. Available: {list(_GATE_SET_REGISTRY)}")
    return loader()


# ── Auto-import domain grids to trigger registration ─────────────────────────
# Import order matters: modules call register_domain() / register_gate_set()
# at import time, so they must be imported after the registry functions are defined.

from . import code as _code  # noqa: E402, F401
from . import infra as _infra  # noqa: E402, F401
from . import prompt as _prompt  # noqa: E402, F401
from . import prose as _prose  # noqa: E402, F401
from . import web as _web  # noqa: E402, F401
from . import phase_early as _phase_early  # noqa: E402, F401
