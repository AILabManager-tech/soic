"""SOIC v3 — Profile system for NEXOS pipeline quality gate thresholds."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class SOICConfig:
    """Configuration for a SOIC profile — phase thresholds and scoring weights."""
    phase_thresholds: Dict[str, float] = field(default_factory=dict)
    min_mu: float = 8.0

    def with_threshold(self, phase: str, target: float) -> "SOICConfig":
        """Return a copy with a specific phase threshold overridden."""
        new_thresholds = dict(self.phase_thresholds)
        new_thresholds[phase] = target
        return SOICConfig(phase_thresholds=new_thresholds, min_mu=target)


@dataclass
class SOICProfile:
    """Named SOIC profile bundling a config for a specific stack/context."""
    name: str
    config: SOICConfig


# ── Built-in profiles ─────────────────────────────────────────────────────────

_PROFILES: Dict[str, SOICProfile] = {
    "web-nextjs": SOICProfile(
        name="web-nextjs",
        config=SOICConfig(
            phase_thresholds={
                "ph0-discovery": 7.0,
                "ph1-strategy": 8.0,
                "ph2-design": 8.0,
                "ph3-content": 8.0,
                "ph4-build": 8.0,
                "ph5-qa": 8.5,
            },
            min_mu=8.0,
        ),
    ),
    "web-generic": SOICProfile(
        name="web-generic",
        config=SOICConfig(
            phase_thresholds={
                "ph0-discovery": 7.0,
                "ph1-strategy": 7.5,
                "ph2-design": 7.5,
                "ph3-content": 7.5,
                "ph4-build": 7.5,
                "ph5-qa": 8.0,
            },
            min_mu=7.5,
        ),
    ),
    "api-fastapi": SOICProfile(
        name="api-fastapi",
        config=SOICConfig(
            phase_thresholds={
                "ph0-discovery": 7.0,
                "ph1-strategy": 8.0,
                "ph2-design": 8.0,
                "ph3-content": 7.0,
                "ph4-build": 8.5,
                "ph5-qa": 8.5,
            },
            min_mu=8.0,
        ),
    ),
}

_DEFAULT_PROFILE = "web-nextjs"


def get_profile(name: str) -> SOICProfile:
    """Return a SOICProfile by name. Falls back to web-nextjs if unknown."""
    return _PROFILES.get(name, _PROFILES[_DEFAULT_PROFILE])


def list_profiles() -> list[str]:
    """Return all available profile names."""
    return list(_PROFILES.keys())
