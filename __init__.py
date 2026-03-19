"""SOIC v3.0 — Tool-verified quality gates.

Consolidated engine: domain-based (code) + phase-based (web/NEXOS).
"""

from .converger import Converger, Decision, WebConverger
from .dimensions import DIMENSIONS, calculate_mu
from .gate_engine import GateEngine
from .gate_protocol import WebGate
from .iterator import LoopResult, PhaseIterator, SOICIterator
from .models import (
    DeltaReport,
    GateReport,
    GateResult,
    GateStatus,
    PhaseGateReport,
    SOICScore,
)
from .persistence import RunStore

__all__ = [
    "Converger",
    "Decision",
    "DeltaReport",
    "DIMENSIONS",
    "GateEngine",
    "GateReport",
    "GateResult",
    "GateStatus",
    "LoopResult",
    "PhaseGateReport",
    "PhaseIterator",
    "RunStore",
    "SOICIterator",
    "SOICScore",
    "WebConverger",
    "WebGate",
    "calculate_mu",
]
