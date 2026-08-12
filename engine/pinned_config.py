"""
Pinned call definition (plan 01-006 / Dograh frozen workflow_run.definition).

Snapshot of config at call start so mid-call dashboard edits cannot drift
temperature, prompt, or interrupt policy for an in-flight conversation.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

# Keys that must not change mid-call once pinned
_PIN_KEYS = (
    "lang_preset",
    "agent_instructions",
    "first_line",
    "llm_model",
    "gemini_model",
    "llm_temperature",
    "llm_max_completion_tokens",
    "tts_provider",
    "tts_voice",
    "tts_language",
    "stt_provider",
    "stt_language",
    "interrupt_min_duration",
    "interrupt_min_words",
    "max_turns",
    "filler_phrases_enabled",
    "speculative_reply_enabled",
    "iq_enabled",
    "prompt_version",
    "system_prompt_token_budget",
    "llm_tiered_retry_ms",
    "llm_tiered_hard_cap_ms",
)


def pin_call_config(live_config: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-frozen subset; also stores on live_config['_pinned']."""
    pinned = {k: copy.deepcopy(live_config.get(k)) for k in _PIN_KEYS if k in live_config}
    pinned["_pinned_at"] = __import__("time").time()
    live_config["_pinned"] = pinned
    live_config["_config_hash"] = config_hash(pinned)
    return pinned


def config_hash(pinned_or_config: dict[str, Any]) -> str:
    payload = {k: pinned_or_config.get(k) for k in sorted(_PIN_KEYS)}
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def read_pinned(live_config: dict[str, Any], key: str, default: Any = None) -> Any:
    pinned = live_config.get("_pinned") or {}
    if key in pinned:
        return pinned[key]
    return live_config.get(key, default)
