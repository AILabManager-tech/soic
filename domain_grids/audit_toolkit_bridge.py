"""SOIC v3 ↔ audit_toolkit bridge.

Registers the audit_toolkit gates (W-21..W-27) as a gate set named
AUDIT_TOOLKIT so they can be loaded via get_phase_gates() or directly.

Usage:
    from soic_v3.domain_grids import get_phase_gates
    gates = get_phase_gates("ph5-qa")  # includes AUDIT_TOOLKIT gates
"""

from __future__ import annotations

try:
    from audit_toolkit.gates.seo_gates import (
        run_all_gates as _run_all_toolkit_gates,
        _GATE_REGISTRY,
        GateResult,
    )

    _HAS_AUDIT_TOOLKIT = True
except ImportError:
    _HAS_AUDIT_TOOLKIT = False


class _AuditToolkitGateWrapper:
    """Wraps an audit_toolkit gate as a callable compatible with GateEngine.

    GateEngine expects objects with a .run(client_dir, site_dir) method
    returning a GateResult.  This wrapper translates that interface to
    the audit_toolkit gate runner.
    """

    def __init__(self, gate_id: str, dimension: str, name: str):
        self.gate_id = gate_id
        self.dimension = dimension
        self.name = name

    def run(self, client_dir: str, site_dir: str) -> GateResult:
        from audit_toolkit.gates.seo_gates import run_gate

        return run_gate(self.gate_id, site_dir)


def _load_audit_toolkit_gates() -> list:
    """Load all audit_toolkit gates as wrapper objects."""
    if not _HAS_AUDIT_TOOLKIT:
        return []
    return [
        _AuditToolkitGateWrapper(gid, dim, label)
        for gid, (dim, label, *_rest) in _GATE_REGISTRY.items()
    ]


# Registration is handled lazily in __init__.py to avoid circular imports
# (seo_gates → soic_v3.models → soic_v3.__init__ → bridge → seo_gates).
