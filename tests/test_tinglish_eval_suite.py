"""09-001 — Tinglish 50-utterance suite structural checks + intent heuristics."""
from __future__ import annotations

import json
from pathlib import Path

SUITE = Path(__file__).parent / "eval" / "tinglish_50_utterances.json"


def test_suite_has_50():
    data = json.loads(SUITE.read_text(encoding="utf-8"))
    utts = data["utterances"]
    assert len(utts) == 50
    ids = {u["id"] for u in utts}
    assert len(ids) == 50
    for u in utts:
        assert u["text"].strip()
        assert "expect" in u


def test_identity_utterances_trigger_shield():
    from identity_shield import handle_identity_trap_turn

    data = json.loads(SUITE.read_text(encoding="utf-8"))
    identity = [u for u in data["utterances"] if u["expect"].get("intent") == "identity"]
    assert identity, "suite must include identity traps"
    hits = 0
    for u in identity:
        d = handle_identity_trap_turn(
            u["text"],
            lang="en-in",
            backstory={"name": "Arjun", "company": "VK Realty", "role": "consultant"},
            preset="tinglish",
        )
        if d:
            hits += 1
    assert hits >= 1, "identity shield should catch at least one suite trap"


def test_response_length_policy_on_suite():
    from conversational_iq import ResponseLengthPolicy

    data = json.loads(SUITE.read_text(encoding="utf-8"))
    for u in data["utterances"][:10]:
        mn, mx = ResponseLengthPolicy.classify_expected_length(u["text"], turn_count=3)
        assert 1 <= mn <= mx <= 60
