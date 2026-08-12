"""Preset-agnostic reply PCM cache lookup."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from preset_contract import min_reply_variants_for_preset, reply_variants_for_preset
from reply_cache import clear_reply_cache_index, lookup_reply_pcm, register_reply_pcm


def test_reply_variants_from_json_tinglish():
    variants = reply_variants_for_preset("tinglish")
    assert len(variants) >= min_reply_variants_for_preset("tinglish")


def test_reply_variants_from_json_hme():
    variants = reply_variants_for_preset("hme")
    assert len(variants) >= 20


def test_normalized_reply_cache_lookup():
    clear_reply_cache_index()
    canonical = "Sare andi, budget range entha rough ga cheppandi?"
    register_reply_pcm(canonical, b"\x00\x01", lang_preset="tinglish")

    pcm, _ = lookup_reply_pcm(
        "Sare andi, budget range entha rough ga cheppandi.",
        lang_preset="tinglish",
    )
    assert pcm == b"\x00\x01"

    pcm2, _ = lookup_reply_pcm(
        "  Sare  andi,  budget range entha rough ga cheppandi?  ",
        lang_preset="tinglish",
    )
    assert pcm2 == b"\x00\x01"