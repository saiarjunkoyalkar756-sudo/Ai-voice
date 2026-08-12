"""Golden-string tests for tts_normalizer — 30 production cases."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tts_normalizer import normalize_for_tts

GOLDEN = [
    ("1.2 Cr", "one point two crores"),
    ("1.2 Crore", "one point two crores"),
    ("85 L", "eighty five lakhs"),
    ("85 Lakhs", "eighty five lakhs"),
    ("2BHK", "two B H K"),
    ("3 BHK", "three B H K"),
    ("4BHK flat", "four B H K flat"),
    ("1500 sqft", "one thousand five hundred square feet"),
    ("1,200 sqft", "one thousand two hundred square feet"),
    ("7200 per sqft", "seven thousand two hundred per square foot"),
    ("Kokapet lo 3 BHK price 1.2 Cr", "Kokapet lo three B H K price one point two crores"),
    ("Budget 80 lakhs", "Budget eighty lakhs"),
    ("EMI for 90 L loan", "EMI for ninety lakhs loan"),
    ("9876543210", "nine eight seven six five four three two one zero"),
    ("+919876543210", "plus nine one nine eight seven six five four three two one zero"),
    ("Rate 7,200 per sqft undi", "Rate seven thousand two hundred per square foot undi"),
    ("2.34 Cr starting", "two point three four crores starting"),
    ("95 L nunchi", "ninety five lakhs nunchi"),
    ("Site visit Saturday", "Site visit Saturday"),
    ("andi garu", "andi garu"),
    ("one crore already spoken", "one crore already spoken"),
    ("12 hundred sqft", "12 hundred sqft"),
    ("Possession December 2027", "Possession December 2027"),
    ("RERA approved", "RERA approved"),
    ("Financial District", "Financial District"),
    ("My Home Krishe 3BHK", "My Home Krishe three B H K"),
    ("1 Cr vs 1.5 Cr", "one crores vs one point five crores"),
    ("Call me 9123456789", "Call me nine one two three four five six seven eight nine"),
    ("0.95 Cr", "zero point nine five crores"),
    ("10 L down payment", "ten lakhs down payment"),
]


@pytest.mark.parametrize("raw,expected", GOLDEN)
def test_golden_normalize(raw: str, expected: str):
    result = normalize_for_tts(raw, lang_preset="tinglish")
    assert expected in result or result == expected, f"got {result!r}, want {expected!r}"