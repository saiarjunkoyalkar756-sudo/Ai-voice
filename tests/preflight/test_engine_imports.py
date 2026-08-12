"""Preflight: all critical production modules import cleanly."""
from __future__ import annotations

import importlib

import pytest

CRITICAL_MODULES = [
    "agent",
    "engine",
    "engine.agent_runtime",
    "engine.conversation_engine",
    "engine.metrics.turn_metrics",
    "engine.ttft_policy",
    "engine.active_calls",
    "engine.canary",
    "call_quality_scorer",
    "stt_provider",
    "tts_provider",
    "gemini_llm",
    "cartesia_tts",
    "token_counter",
    "turn_context_injection",
    "language_router",
    "preset_contract",
    "knowledge_pack",
    "circuit_breaker",
    "llm_tiered_guard",
    "indic_sentence_tokenizer",
    "tts_text_transform",
    "identity_shield",
    "prompt_compiler",
    "config_store",
    "ui_server",
    "ship.packager",
    "ship.secrets",
]


@pytest.mark.parametrize("mod", CRITICAL_MODULES)
def test_import_critical_module(mod: str):
    importlib.import_module(mod)


def test_engine_version():
    import engine

    assert hasattr(engine, "__version__")
