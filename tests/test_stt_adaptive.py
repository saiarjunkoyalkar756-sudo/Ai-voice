"""Adaptive Soniox endpoint delay — preset-agnostic short-utterance fast close."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from stt_provider import compute_adaptive_endpoint_delay_ms


def test_adaptive_disabled_uses_base():
    cfg = {"stt_max_endpoint_delay_ms": 350, "stt_adaptive_endpoint_enabled": False}
    assert compute_adaptive_endpoint_delay_ms(cfg, "budget entha") == 350


def test_adaptive_short_utterance():
    cfg = {"stt_max_endpoint_delay_ms": 350, "stt_adaptive_endpoint_enabled": True}
    assert compute_adaptive_endpoint_delay_ms(cfg, "80 lakhs range") <= 300


def test_adaptive_long_utterance():
    cfg = {"stt_max_endpoint_delay_ms": 350, "stt_adaptive_endpoint_enabled": True}
    long_text = "Nenu Gachibowli side lo 3BHK chustunnanu budget one crore varaku"
    assert compute_adaptive_endpoint_delay_ms(cfg, long_text) == 350