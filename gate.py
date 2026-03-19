"""SOIC v3.0 — Quality Gate.

Legacy wrapper: delegates to GateEngine for backward compatibility.
"""

from pathlib import Path

from .gate_engine import GateEngine


def evaluate_gate(phase: str, client_dir: Path) -> float:
    """Evaluate the quality gate for a phase. Returns mu (0.0-10.0).

    This is the legacy entry point. New code should use GateEngine directly.
    """
    engine = GateEngine(phase=phase, client_dir=str(client_dir))
    report = engine.run_all_gates()
    return report.mu
