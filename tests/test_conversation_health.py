"""Conversation health wave — turn injection."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from turn_context_injection import _conversation_health_message


def test_health_silent_when_few_turns():
    assert _conversation_health_message({}) is None
    assert _conversation_health_message({"_recent_agent_replies": ["Hi andi?"]}) is None


def test_health_flags_long_turns_without_question():
    live = {
        "_recent_agent_replies": [
            "Kokapet lo options chala unnayi. Godrej undi. Prestige undi. My Home kuda undi.",
            "Budget flexible aite ASBL kuda chudochu. Rates konchem vary avutayi.",
        ]
    }
    msg = _conversation_health_message(live)
    assert msg is not None
    assert "CONVERSATION HEALTH" in msg
    assert "question" in msg.lower()


def test_health_ok_when_short_with_question():
    live = {
        "_recent_agent_replies": [
            "Sare andi, Kokapet side prefer chestunnara?",
            "Budget entha rough ga cheppandi?",
        ]
    }
    assert _conversation_health_message(live) is None