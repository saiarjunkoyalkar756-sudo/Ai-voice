"""
Canary rollout helpers (plan 07-005) — wraps agent_config_loader with engine flags.
"""
from __future__ import annotations

from typing import Any


def apply_engine_canary(live_config: dict[str, Any], seed: str) -> dict[str, Any]:
    """Apply prompt canary + enable IQ v2 / parallel injectors for canary bucket."""
    from agent_config_loader import apply_canary_to_live_config

    merged = apply_canary_to_live_config(live_config, seed)
    if merged.get("is_canary"):
        # Safer production canary feature bundle
        merged.setdefault("conversational_iq_v2_enabled", True)
        merged.setdefault("parallel_turn_injectors_enabled", True)
        merged.setdefault("speculative_reply_enabled", True)
        merged.setdefault("engine_pipeline_v1", True)
    else:
        # Stable path: engine metrics always on; IQ v2 opt-in via env/config
        merged.setdefault("engine_pipeline_v1", True)
        if merged.get("conversational_iq_v2_enabled") is None:
            import os

            env_iq = os.environ.get("VOICELY_IQ_V2", "").strip().lower()
            if env_iq in ("1", "true", "yes", "on"):
                merged["conversational_iq_v2_enabled"] = True
            elif env_iq in ("0", "false", "no", "off"):
                merged["conversational_iq_v2_enabled"] = False
            else:
                # Default: enable IQ v2 for all traffic once metrics exist (prod target)
                merged.setdefault("conversational_iq_v2_enabled", True)
        merged.setdefault("parallel_turn_injectors_enabled", True)
    return merged
