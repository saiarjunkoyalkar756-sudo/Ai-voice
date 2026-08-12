"""
Soniox / STT context expansion from knowledge packs (plan 08-001).

Merges persona stt_hints + inventory names + hot aliases into a context list
for the STT provider (Soniox context / keyterms).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("speaksy-engine")

_MAX_TERMS = 40


def expand_stt_context(live_config: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        t = (raw or "").strip()
        if len(t) < 2 or len(t) > 48:
            return
        key = t.casefold()
        if key in seen:
            return
        seen.add(key)
        terms.append(t)

    for h in live_config.get("stt_hints") or []:
        _add(str(h))

    persona = live_config.get("_persona_pack") or live_config.get("persona") or {}
    if isinstance(persona, dict):
        for h in persona.get("stt_hints") or []:
            _add(str(h))
        _add(str(persona.get("name") or ""))
        _add(str(persona.get("company") or ""))

    # Inventory / knowledge pack names
    try:
        from knowledge_pack import get_store
        from language_router import resolve_lang_preset
        from preset_contract import knowledge_pack_id_for

        preset = resolve_lang_preset(live_config.get("lang_preset"), live_config)
        pack_id = knowledge_pack_id_for(preset)
        store = get_store()
        pack = getattr(store, "_packs", {}).get(pack_id) if hasattr(store, "_packs") else None
        listings = {}
        if isinstance(pack, dict):
            listings = pack.get("listings") or pack.get("properties") or {}
        # KnowledgeStore may expose differently
        if not listings and hasattr(store, "list_listing_names"):
            try:
                for n in store.list_listing_names(pack_id) or []:
                    _add(str(n))
            except Exception:
                pass
        if isinstance(listings, dict):
            for lid, item in list(listings.items())[:20]:
                if isinstance(item, dict):
                    _add(str(item.get("name") or lid))
                    for a in (item.get("aliases") or [])[:3]:
                        _add(str(a))
                else:
                    _add(str(lid))
        aliases_map = getattr(store, "_listing_aliases", {}).get(pack_id) or {}
        for alias in list(aliases_map.keys())[:25]:
            _add(alias.replace("_", " "))
    except Exception as exc:
        logger.debug("[STT-CTX] pack expand skipped: %s", exc)

    # Domain anchors
    for anchor in (
        "Gachibowli",
        "Kokapet",
        "Neopolis",
        "RERA",
        "2BHK",
        "3BHK",
        "site visit",
        "EMI",
    ):
        _add(anchor)

    out = terms[:_MAX_TERMS]
    live_config["_stt_context_terms"] = out
    return out
