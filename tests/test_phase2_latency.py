"""Phase 2 — prompt compiler, tool stage filter, stable-prefix turn context."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from livekit.agents import llm

from prompt_compiler import compile_system_prompt
from sales_playbook import DealStage
from tool_stage_registry import allowed_tool_names, filter_tools_for_stage
from turn_context_injection import (
    apply_turn_context_to_user_message,
    format_turn_context_suffix,
    TurnInjectionResult,
)


def test_compile_prompt_within_budget():
    live_config = {
        "lang_preset": "tinglish",
        "agent_instructions": "You are Arjun, a VK Realty consultant.",
        "system_prompt_token_budget": 800,
        "tts_provider": "cartesia",
    }
    compiled = compile_system_prompt(live_config, lang_preset="tinglish", strict=False)
    assert compiled.token_count <= compiled.budget
    assert compiled.text.strip()
    assert "[TURN CONTEXT —" not in compiled.text


def test_stage_tool_filter_limits_to_four():
    allowed = allowed_tool_names(DealStage.AWARENESS)
    assert len(allowed) == 4
    assert "end_call" in allowed
    assert "transfer_call" not in allowed


def test_format_turn_context_suffix():
    suffix = format_turn_context_suffix(["Price FAQ", "Stage: interest"])
    assert "[TURN CONTEXT" in suffix
    assert "Price FAQ" in suffix


def test_apply_turn_context_updates_user_message():
    ctx = llm.ChatContext()
    msg = llm.ChatMessage(role="user", content=["What is the price?"])
    ctx.add_message(role="user", content="What is the price?")
    result = TurnInjectionResult(messages=["3BHK from 1.15 Cr"])
    ok = apply_turn_context_to_user_message(ctx, msg, result)
    assert ok is True
    assert "What is the price?" in ctx.items[-1].text_content
    assert "3BHK" in ctx.items[-1].text_content
    assert "[TURN CONTEXT" in ctx.items[-1].text_content