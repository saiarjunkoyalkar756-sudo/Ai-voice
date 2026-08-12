"""
LLM TTFT hard-cap tiers (plan 03-002).

Defaults tightened from 3000ms silent SLA → tiered 1500 retry / 1800 hard cap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TTFTPolicy:
    """Production best-fit (hme / Operation Sub-Second proven path).

    Circuit breaker + tiered guard share hard_cap_ms (default 3000).
    """
    warn_ms: float = 800.0
    retry_ms: float = 1500.0
    hard_cap_ms: float = 3000.0  # production best-fit SLA


def resolve_ttft_policy(live_config: dict[str, Any] | None = None) -> TTFTPolicy:
    cfg = live_config or {}
    hard = cfg.get("llm_tiered_hard_cap_ms")
    if hard is None:
        hard = cfg.get("llm_circuit_sla_ms", 3000.0)
    return TTFTPolicy(
        warn_ms=float(cfg.get("llm_ttft_warn_ms", 800.0)),
        retry_ms=float(cfg.get("llm_tiered_retry_ms", 1500.0)),
        hard_cap_ms=float(hard),
    )


def apply_ttft_defaults(live_config: dict[str, Any]) -> TTFTPolicy:
    """Ensure live_config has production TTFT knobs (non-destructive)."""
    policy = resolve_ttft_policy(live_config)
    live_config.setdefault("llm_ttft_warn_ms", policy.warn_ms)
    live_config.setdefault("llm_tiered_retry_ms", policy.retry_ms)
    live_config.setdefault("llm_tiered_hard_cap_ms", policy.hard_cap_ms)
    return policy
