"""Load preset contract from data/preset_schema.json — single source for language_router."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("inbound-voice-agent")

_SCHEMA_PATH = Path(__file__).resolve().parent / "data" / "preset_schema.json"
_REPLY_VARIANTS_PATH = Path(__file__).resolve().parent / "data" / "preset_reply_variants.json"


@lru_cache(maxsize=1)
def load_preset_schema() -> dict[str, Any]:
    if not _SCHEMA_PATH.is_file():
        return {"presets": {}}
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[PRESET-SCHEMA] Failed to load %s: %s", _SCHEMA_PATH, exc)
        return {"presets": {}}


def get_preset_contract(preset_id: str | None) -> dict[str, Any] | None:
    key = (preset_id or "tinglish").strip().lower()
    presets = load_preset_schema().get("presets") or {}
    contract = presets.get(key)
    return dict(contract) if isinstance(contract, dict) else None


def interrupt_pool_for(preset_id: str | None) -> list[str]:
    contract = get_preset_contract(preset_id)
    pool = (contract or {}).get("interrupt_pool") or []
    return [str(p) for p in pool if p]


def knowledge_pack_id_for(preset_id: str | None) -> str:
    contract = get_preset_contract(preset_id)
    if contract:
        return str(contract.get("knowledge_pack_id") or preset_id or "tinglish")
    return preset_id or "tinglish"


@lru_cache(maxsize=1)
def load_reply_variants_schema() -> dict[str, Any]:
    if not _REPLY_VARIANTS_PATH.is_file():
        return {"presets": {}}
    try:
        return json.loads(_REPLY_VARIANTS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[PRESET-REPLIES] Failed to load %s: %s", _REPLY_VARIANTS_PATH, exc)
        return {"presets": {}}


_PRESET_KEY_ALIASES: dict[str, str] = {
    "telugu": "tinglish",
    "telugish": "tinglish",
    "multilingual": "tinglish",
    "hi_en_mr": "hme",
    "hinglish": "hme",
    "hindi": "hme",
    "marathi": "hme",
}


def _resolve_preset_key(preset_id: str | None) -> str:
    raw = (preset_id or "tinglish").strip().lower()
    return _PRESET_KEY_ALIASES.get(raw, raw)


def list_preset_ids() -> list[str]:
    presets = load_preset_schema().get("presets") or {}
    return sorted(str(k) for k in presets if k)


def languages_for_preset(preset_id: str | None) -> list[str]:
    contract = get_preset_contract(_resolve_preset_key(preset_id))
    langs = (contract or {}).get("languages") or []
    return [str(x) for x in langs if x]


def default_language_for_preset(preset_id: str | None) -> str:
    contract = get_preset_contract(_resolve_preset_key(preset_id))
    if contract and contract.get("default_language"):
        return str(contract["default_language"])
    langs = languages_for_preset(preset_id)
    return langs[0] if langs else "en-in"


def idle_lines_for_preset(preset_id: str | None) -> dict[str, str]:
    contract = get_preset_contract(_resolve_preset_key(preset_id))
    idle = (contract or {}).get("idle_lines") or {}
    if not isinstance(idle, dict):
        return {}
    return {
        "prompt_message": str(idle.get("prompt") or idle.get("prompt_message") or "").strip(),
        "last_message": str(idle.get("last") or idle.get("last_message") or "").strip(),
    }


def backchannel_pool_for(preset_id: str | None) -> list[str]:
    contract = get_preset_contract(preset_id)
    pool = (contract or {}).get("backchannel_pool") or []
    return [str(p) for p in pool if p]


def first_line_for_preset(preset_id: str | None) -> str:
    contract = get_preset_contract(_resolve_preset_key(preset_id))
    return str((contract or {}).get("first_line") or "").strip()


def stt_hints_for_preset(preset_id: str | None) -> list[str]:
    contract = get_preset_contract(_resolve_preset_key(preset_id))
    hints = (contract or {}).get("stt_hints") or []
    return [str(h) for h in hints if h]


def reply_variants_for_preset(preset_id: str | None) -> list[str]:
    """
    Flatten stage-grouped reply lines for prebake + cache lookup.

    Source: data/preset_reply_variants.json → presets[preset_id].stages.*
    Fallback: legacy Python constants in greeting_cache (deprecated).
    """
    key = _resolve_preset_key(preset_id)
    schema = load_reply_variants_schema().get("presets") or {}
    entry = schema.get(key)
    if isinstance(entry, dict):
        stages = entry.get("stages") or {}
        lines: list[str] = []
        seen: set[str] = set()
        for stage_lines in stages.values():
            if not isinstance(stage_lines, list):
                continue
            for raw in stage_lines:
                text = str(raw or "").strip()
                if text and text not in seen:
                    seen.add(text)
                    lines.append(text)
        if lines:
            return lines

    from greeting_cache import HME_REPLY_VARIANTS, TINGLISH_REPLY_VARIANTS
    from language_router import HME_PRESET

    if key == HME_PRESET:
        return list(HME_REPLY_VARIANTS)
    return list(TINGLISH_REPLY_VARIANTS)


def min_reply_variants_for_preset(preset_id: str | None) -> int:
    key = _resolve_preset_key(preset_id)
    schema = load_reply_variants_schema().get("presets") or {}
    entry = schema.get(key) or {}
    try:
        return int(entry.get("min_variants") or 35)
    except (TypeError, ValueError):
        return 35


def clear_preset_contract_cache() -> None:
    load_preset_schema.cache_clear()
    load_reply_variants_schema.cache_clear()