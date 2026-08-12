"""First-chunk fast path for TTS."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from indic_sentence_tokenizer import is_tts_ready_chunk, pop_speakable_tts_chunk


def test_first_chunk_flushes_short_ack():
    text = "Sare andi,"
    assert is_tts_ready_chunk(text, first_chunk=True) is True
    chunk, leftover = pop_speakable_tts_chunk(text, first_chunk=True)
    assert chunk == text
    assert leftover == ""


def test_non_first_chunk_waits_longer():
    text = "Sare andi,"
    assert is_tts_ready_chunk(text, first_chunk=False) is False