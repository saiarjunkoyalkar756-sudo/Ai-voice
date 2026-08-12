"""09-002 — Golden call regression skeleton (offline, no LiveKit)."""
from __future__ import annotations

import json
from pathlib import Path

GOLDEN = Path(__file__).parent / "eval" / "golden_calls.json"


def test_golden_suite_shape():
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(data["calls"]) >= 5
    for c in data["calls"]:
        assert c["id"]
        assert c["turns"]


def test_golden_identity_trap_offline():
    from identity_shield import handle_identity_trap_turn

    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    gc = next(c for c in data["calls"] if c["id"] == "gc-identity-trap")
    text = gc["turns"][0]["text"]
    reply = handle_identity_trap_turn(
        text,
        lang="en-in",
        backstory={"name": "Arjun", "company": "VK Realty", "role": "consultant"},
        preset="tinglish",
    )
    assert reply, "identity trap must short-circuit"
    lowered = reply.lower()
    for banned in gc.get("must_not_contain_agent") or []:
        assert banned.lower() not in lowered
