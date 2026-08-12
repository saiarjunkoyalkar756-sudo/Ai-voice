"""Fuzzy inventory alias matching — <3ms resolve budget (P3.14 / B3)."""
from __future__ import annotations

import os
import sys
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from knowledge_pack import get_store, preload_knowledge_packs


@pytest.fixture(scope="module", autouse=True)
def _load_packs():
    preload_knowledge_packs()


@pytest.mark.parametrize(
    "utterance",
    [
        "krishe price entha",
        "krishay rate",
        "madison heights pricing",
        "clairmont cost",
        "clairemont rate per sqft",
        "broadway project details",
        "Godrej Madison Avenue",
        "My Home Krishe possession",
        "prestige clairmont gachibowli",
        "kokapet madison 3bhk",
    ],
)
def test_fuzzy_inventory_alias(utterance: str):
    lines = get_store().lookup_inventory(utterance, "tinglish", force=True)
    assert lines, f"expected inventory hit for {utterance!r}"


def test_inventory_resolve_under_3ms():
    store = get_store()
    samples = ["krishe", "madison rate", "broadway EMI", "prestige clairmont"]
    start = time.perf_counter()
    for phrase in samples:
        store.lookup_inventory(phrase, "tinglish", force=True)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 12.0, f"4 lookups took {elapsed_ms:.2f}ms (budget ~3ms each)"