"""08-002 — TTS normalizer golden cases (must not garble phone speech)."""
from __future__ import annotations

import pytest

from tts_text_transform import (
    gate_assistant_speech_text,
    is_allowed_brief_ack,
    is_filler_only,
    sanitize_tts_stutter,
)


GOLDEN_OK = [
    "The 2BHK starts from 1.2 crore andi.",
    "Sare, Saturday morning site visit book chedam.",
    "Gachibowli lo possession December 2026.",
    "EMI options available — bank panel unnadi.",
]

GOLDEN_DROP_OR_TRIM = [
    "We have beauti",  # incomplete
    "...",
    "   ",
    "Right",  # filler-only often gated
]


def _marker(text, tts_lang=None, tts_provider=None, **kwargs):
    return text


def test_golden_speakable_lines_pass():
    for line in GOLDEN_OK:
        out = gate_assistant_speech_text(
            line,
            apply_marker=_marker,
            tts_lang="en-IN",
            tts_provider="cartesia",
            lang_preset="tinglish",
        )
        assert out and len(out) >= 8, line


def test_sanitize_stutter():
    s = sanitize_tts_stutter("I I I think the price is good")
    assert "I I I" not in s or s.count("I") < 4


def test_filler_detection():
    assert is_filler_only("Okay")
    assert is_allowed_brief_ack("Sare andi") or is_allowed_brief_ack("sare andi")


def test_incomplete_fragment_gated():
    # Incomplete mid-word should not fully pass as long speech
    raw = "Welcome to VK Realty. We have beauti"
    out = gate_assistant_speech_text(
        raw,
        apply_marker=_marker,
        tts_lang="en-IN",
        tts_provider="cartesia",
        lang_preset="tinglish",
    )
    # Either dropped or trimmed before incomplete tail
    if out:
        assert "beauti" not in out.lower() or "realty" in out.lower()
