"""Engine package smoke + unit tests (VOICELY_ENGINE_MASTER_PLAN Phase 0–1)."""
from __future__ import annotations

import asyncio

import pytest


def test_engine_imports():
    from engine import (
        ConversationEngine,
        TurnMetrics,
        TurnMetricsCollector,
        TurnResult,
        TurnStage,
        config_hash,
        get_registry,
        pin_call_config,
    )
    from engine.pipeline_stages import PIPELINE_STAGES, stage_names
    from engine.interrupt_policy import resolve_interrupt_policy
    from engine.ttft_policy import apply_ttft_defaults, resolve_ttft_policy

    assert len(PIPELINE_STAGES) == 6
    assert stage_names()[0] == "stt_final"
    assert TurnStage.LLM_TTFT.value == "llm_ttft"


def test_turn_metrics_collector_stages():
    from engine.metrics.turn_metrics import TurnMetricsCollector, TurnStage

    c = TurnMetricsCollector(room_id="room-1", config_hash="abc")
    c.begin_turn(1, transcript="hello", adaptive_endpoint_ms=120.0)
    c.note_inject(45.0)
    c.note_llm_ttft(300.0)
    c.note_tts_ttfa(80.0, reply_cache_hit=False)
    m = c.end_turn()
    assert m is not None
    rows = c.rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["stages_ms"]["stt_final"] == 120.0
    assert row["stages_ms"]["turn_inject"] == 45.0
    assert row["stages_ms"]["llm_ttft"] == 300.0
    assert row["stages_ms"]["tts_ttfa"] == 80.0
    assert row["e2e_ms"] is not None
    exp = c.export()
    assert exp["schema"] == "voicely.turn_metrics.v1"
    assert "stage_p50" in exp


def test_active_call_registry_drain():
    from engine.active_calls import ActiveCallRegistry

    reg = ActiveCallRegistry()
    reg.register("r1", phone="+9199", direction="inbound")
    reg.register("r2", phone="+9188")
    assert reg.count() == 2
    snap = reg.snapshot()
    assert snap["active"] == 2
    assert snap["drain_ready"] is False
    reg.unregister("r1")
    reg.unregister("r2")
    assert reg.snapshot()["drain_ready"] is True


def test_pinned_config_hash_stable():
    from engine.pinned_config import config_hash, pin_call_config

    cfg = {
        "lang_preset": "tinglish",
        "llm_temperature": 0.55,
        "llm_max_completion_tokens": 100,
        "tts_provider": "cartesia",
    }
    pin_call_config(cfg)
    h1 = cfg["_config_hash"]
    h2 = config_hash(cfg["_pinned"])
    assert h1 == h2
    assert len(h1) == 16


def test_ttft_policy_defaults():
    from engine.ttft_policy import apply_ttft_defaults

    cfg: dict = {}
    p = apply_ttft_defaults(cfg)
    # Production best-fit (hme): 3000ms circuit SLA / hard cap
    assert p.hard_cap_ms == 3000.0
    assert p.retry_ms == 1500.0
    assert cfg["llm_tiered_hard_cap_ms"] == 3000.0


def test_interrupt_policy_booking_phase():
    from engine.interrupt_policy import resolve_interrupt_policy

    class T:
        stage = "book"

    pol = resolve_interrupt_policy({"_deal_tracker": T()})
    assert pol.allow_interrupt is False
    assert pol.phase == "book"


def test_conversation_engine_identity_trap(monkeypatch):
    from engine.conversation_engine import ConversationEngine

    def _fake_trap(transcript, lang, backstory, preset):
        if "are you ai" in transcript.lower():
            return "I'm Arjun from the sales team — how can I help?"
        return None

    monkeypatch.setattr(
        "identity_shield.handle_identity_trap_turn",
        _fake_trap,
    )
    monkeypatch.setattr(
        "identity_shield.load_backstory",
        lambda cfg: {"name": "Arjun", "company": "VK Realty"},
    )
    monkeypatch.setattr(
        "language_router.resolve_turn_language",
        lambda *a, **k: "en-in",
    )
    monkeypatch.setattr(
        "language_router.apply_language_to_config",
        lambda cfg, lang: {"detected_language": lang},
    )

    eng = ConversationEngine({"lang_preset": "tinglish", "llm_max_completion_tokens": 120})
    result = asyncio.run(eng.on_user_turn("are you AI?", turn=1, run_injections=False))
    assert result.skip_llm is True
    assert result.identity_trap is True
    assert result.scripted_reply and "Arjun" in result.scripted_reply


def test_conversation_engine_length_tokens(monkeypatch):
    from engine.conversation_engine import ConversationEngine

    monkeypatch.setattr("identity_shield.handle_identity_trap_turn", lambda *a, **k: None)
    monkeypatch.setattr("identity_shield.load_backstory", lambda cfg: {})
    monkeypatch.setattr("language_router.resolve_turn_language", lambda *a, **k: "en-in")
    monkeypatch.setattr(
        "language_router.apply_language_to_config",
        lambda cfg, lang: {},
    )

    eng = ConversationEngine({"lang_preset": "tinglish", "llm_max_completion_tokens": 200})
    result = asyncio.run(
        eng.on_user_turn("haan", turn=2, run_injections=False)
    )
    assert result.skip_llm is False
    assert result.max_completion_tokens is not None
    assert result.max_completion_tokens <= 64  # short ack
    assert any("RESPONSE LENGTH" in m for m in result.system_messages)


def test_turn_latency_waterfall():
    from turn_latency import summarize_turn_latencies

    rows = [
        {
            "stages_ms": {
                "stt_final": 100,
                "turn_inject": 40,
                "llm_ttft": 400,
                "tts_ttfa": 60,
            },
            "e2e_ms": 600,
            "ttfa_server_ms": 600,
        },
        {
            "stt_ms": 120,
            "inject_ms": 50,
            "llm_ms": 500,
            "tts_ms": 70,
            "e2e_ms": 740,
        },
    ]
    s = summarize_turn_latencies(rows)
    assert s["count"] == 2
    assert "waterfall_p50" in s
    assert s["waterfall_p50"].get("llm_ttft") is not None
