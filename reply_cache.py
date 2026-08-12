"""
Preset-agnostic reply PCM cache lookup.

Normalizes agent speech text so pre-baked lines match even when the LLM
adds trailing punctuation or spacing. Keys are built at prebake time from
data/preset_reply_variants.json (per preset_id).
"""
from __future__ import annotations

import re
from typing import Any

_REPLY_BY_CANONICAL: dict[str, bytes] = {}
_REPLY_BY_NORM: dict[str, bytes] = {}


def clear_reply_cache_index() -> None:
    _REPLY_BY_CANONICAL.clear()
    _REPLY_BY_NORM.clear()


def cache_lookup_keys(text: str, *, lang_preset: str | None = None) -> list[str]:
    """Generate equivalence keys for reply PCM lookup (order: most specific first)."""
    raw = (text or "").strip()
    if not raw:
        return []

    keys: list[str] = []
    seen: set[str] = set()

    def _add(val: str) -> None:
        v = (val or "").strip()
        if v and v not in seen:
            seen.add(v)
            keys.append(v)

    _add(raw)
    collapsed = re.sub(r"\s+", " ", raw)
    _add(collapsed)
    stripped = collapsed.rstrip(".,!?।")
    _add(stripped)
    lower = stripped.lower()
    _add(lower)

    try:
        from tts_normalizer import normalize_for_tts

        spoken = normalize_for_tts(stripped, lang_preset=lang_preset)
        _add(spoken)
    except Exception:
        pass

    return keys


def register_reply_pcm(
    canonical_text: str,
    pcm: bytes,
    *,
    lang_preset: str | None = None,
) -> None:
    """Index one pre-baked reply line under all normalized lookup keys."""
    if not pcm:
        return
    canonical = (canonical_text or "").strip()
    if not canonical:
        return
    _REPLY_BY_CANONICAL[canonical] = pcm
    for key in cache_lookup_keys(canonical, lang_preset=lang_preset):
        _REPLY_BY_NORM[key] = pcm


def lookup_reply_pcm(text: str, *, lang_preset: str | None = None) -> tuple[bytes | None, bool]:
    """
    Return (pcm, exact_canonical_hit).

    exact_canonical_hit is True when lookup matched the canonical prebake string.
    """
    for key in cache_lookup_keys(text, lang_preset=lang_preset):
        pcm = _REPLY_BY_NORM.get(key)
        if pcm:
            exact = key in _REPLY_BY_CANONICAL and _REPLY_BY_CANONICAL.get(key) == pcm
            if not exact:
                exact = (text or "").strip() in _REPLY_BY_CANONICAL
            return pcm, exact
    canonical = (text or "").strip()
    pcm = _REPLY_BY_CANONICAL.get(canonical)
    if pcm:
        return pcm, True
    return None, False


def reply_cache_stats() -> dict[str, Any]:
    return {
        "canonical_lines": len(_REPLY_BY_CANONICAL),
        "lookup_keys": len(_REPLY_BY_NORM),
    }