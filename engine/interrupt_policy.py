"""
Per-phase interrupt policy matrix (plans 05-001, 05-002).

Maps deal stage → (allow_interrupt, min_duration_ms, min_words).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InterruptPolicy:
    allow_interrupt: bool = True
    min_duration_ms: int = 200
    min_words: int = 0
    phase: str = "default"


# Stage names align with call_planner / DealStageTracker when available
_PHASE_POLICIES: dict[str, InterruptPolicy] = {
    "open": InterruptPolicy(True, 150, 0, "open"),
    "discover": InterruptPolicy(True, 180, 0, "discover"),
    "match": InterruptPolicy(True, 220, 1, "match"),
    "objection": InterruptPolicy(True, 250, 1, "objection"),
    "close": InterruptPolicy(True, 300, 1, "close"),
    "book": InterruptPolicy(False, 500, 2, "book"),  # protect booking confirmation
    "farewell": InterruptPolicy(True, 150, 0, "farewell"),
    "default": InterruptPolicy(True, 200, 0, "default"),
}


def resolve_interrupt_policy(live_config: dict[str, Any] | None) -> InterruptPolicy:
    cfg = live_config or {}
    tracker = cfg.get("_deal_tracker")
    stage = str(getattr(tracker, "stage", None) or cfg.get("deal_stage") or "default").lower()
    # normalize common aliases
    aliases = {
        "opening": "open",
        "discovery": "discover",
        "matching": "match",
        "closing": "close",
        "booking": "book",
        "site_visit": "book",
    }
    stage = aliases.get(stage, stage)
    base = _PHASE_POLICIES.get(stage, _PHASE_POLICIES["default"])

    # Config overrides (dashboard knobs) still win when present
    min_dur = cfg.get("interrupt_min_duration_ms")
    min_words = cfg.get("interrupt_min_words")
    allow = cfg.get("allow_interrupt")
    return InterruptPolicy(
        allow_interrupt=bool(allow) if allow is not None else base.allow_interrupt,
        min_duration_ms=int(min_dur) if min_dur is not None else base.min_duration_ms,
        min_words=int(min_words) if min_words is not None else base.min_words,
        phase=base.phase,
    )
