"""Partial turn tracker — TTFA clock + match ratio."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from partial_turn_tracker import normalized_match_ratio, speculative_partial_unsafe


def test_normalized_match_high_for_same_utterance():
    ratio = normalized_match_ratio("what is the price for 3bhk", "what is the price for 3bhk")
    assert ratio >= 0.99


def test_normalized_match_lower_for_drift():
    ratio = normalized_match_ratio("what is the price", "what is the price for godrej 3bhk")
    assert 0.4 < ratio < 0.95


def test_speculative_unsafe_mid_number():
    assert speculative_partial_unsafe("the price is 1.2") is True
    assert speculative_partial_unsafe("the price is 1.2 crores.") is False