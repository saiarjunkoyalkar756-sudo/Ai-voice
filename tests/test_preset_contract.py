"""Preset contract — schema-driven engine (P3.13 / B4 smoke)."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from preset_contract import (
    default_language_for_preset,
    first_line_for_preset,
    get_preset_contract,
    idle_lines_for_preset,
    knowledge_pack_id_for,
    languages_for_preset,
    list_preset_ids,
    min_reply_variants_for_preset,
    reply_variants_for_preset,
)


def test_schema_lists_core_presets():
    ids = list_preset_ids()
    assert "tinglish" in ids
    assert "hme" in ids
    assert "english" in ids


def test_english_preset_contract_only():
    contract = get_preset_contract("english")
    assert contract is not None
    assert contract["knowledge_pack_id"] == "english"
    assert languages_for_preset("english") == ["en-in"]
    assert default_language_for_preset("english") == "en-in"
    assert knowledge_pack_id_for("english") == "english"
    assert first_line_for_preset("english")
    idle = idle_lines_for_preset("english")
    assert idle.get("prompt_message")
    assert idle.get("last_message")


def test_english_reply_variants_smoke():
    variants = reply_variants_for_preset("english")
    assert len(variants) >= min_reply_variants_for_preset("english")


def test_english_knowledge_pack_loads():
    from knowledge_pack import get_store, preload_knowledge_packs

    preload_knowledge_packs()
    store = get_store()
    lines = store.lookup_inventory("VAPT training", "english", force=True)
    assert lines
    assert any("VAPT" in line for line in lines)