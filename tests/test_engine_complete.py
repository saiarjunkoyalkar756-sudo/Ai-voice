"""Production completeness tests for remaining master-plan modules."""
from __future__ import annotations

import asyncio


def test_tracing_bind_and_span():
    from engine.tracing import bind_trace, get_trace_id, span

    tid = bind_trace("abc123def456")
    assert get_trace_id() == tid
    with span("unit_test", foo=1) as s:
        assert s.trace_id == tid
    assert get_trace_id() == tid


def test_voicemail_phrases():
    from engine.voicemail import classify_call_outcome, transcript_looks_like_voicemail

    assert transcript_looks_like_voicemail("Please leave a message after the tone")
    assert classify_call_outcome(user_turn_count=0, duration_seconds=15) == "voicemail"
    assert classify_call_outcome(user_turn_count=5, duration_seconds=60) == "completed"


def test_interrupt_ack_rebind():
    from engine.interrupt_ack import (
        build_interrupt_rebind_message,
        consume_interrupt_rebind,
        note_interrupt,
    )

    cfg: dict = {"lang_preset": "tinglish"}
    note_interrupt(cfg, "price entha?")
    msg = consume_interrupt_rebind(cfg)
    assert msg and "INTERRUPT" in msg and "price" in msg.lower()
    assert consume_interrupt_rebind(cfg) is None
    assert "DROP" in build_interrupt_rebind_message("hello", lang_preset="english")


def test_returning_opener():
    from engine.returning_opener import build_returning_opener_hint

    h = build_returning_opener_hint(
        caller_name="Ravi", call_count=2, last_project="Madison", lang_preset="tinglish"
    )
    assert h and "RETURNING" in h and "Ravi" in h


def test_canary_enables_iq():
    from engine.canary import apply_engine_canary

    cfg = apply_engine_canary({"lang_preset": "tinglish"}, seed="room-xyz")
    assert "is_canary" in cfg
    assert cfg.get("engine_pipeline_v1") is True
    # stable or canary both get IQ default
    assert "conversational_iq_v2_enabled" in cfg


def test_post_call_metrics_patch():
    from engine.metrics.turn_metrics import TurnMetricsCollector
    from engine.post_call_export import build_call_log_metrics_patch

    c = TurnMetricsCollector(room_id="r1", config_hash="deadbeef")
    c.begin_turn(1, transcript="hi", adaptive_endpoint_ms=100)
    c.note_inject(20)
    c.note_llm_ttft(200)
    c.note_tts_ttfa(50)
    c.end_turn()
    cfg = {"_turn_metrics": c, "_config_hash": "deadbeef", "_trace_id": "t1"}
    patch = build_call_log_metrics_patch(cfg, quality_payload={"ok": True}, latency_export={})
    assert "turn_metrics" in patch
    assert patch["config_hash"] == "deadbeef"
    assert patch.get("felt_latency_p50_ms") is not None or patch["turn_metrics"]["summary"]


def test_stt_context_expand_basic():
    from engine.stt_context_expand import expand_stt_context

    terms = expand_stt_context({"stt_hints": ["Arjun"], "lang_preset": "tinglish"})
    assert "Arjun" in terms
    assert any("BHK" in t or "bhk" in t.lower() for t in terms) or "2BHK" in terms


def test_llm_token_cap_helper():
    from engine.llm_node_helpers import apply_turn_token_cap

    class MS:
        max_completion_tokens = 200

    ms = MS()
    apply_turn_token_cap(ms, {"_turn_max_completion_tokens": 64})
    assert ms.max_completion_tokens == 64


def test_conversation_engine_interrupt_message(monkeypatch):
    from engine.conversation_engine import ConversationEngine
    from engine.interrupt_ack import note_interrupt

    monkeypatch.setattr("identity_shield.handle_identity_trap_turn", lambda *a, **k: None)
    monkeypatch.setattr("identity_shield.load_backstory", lambda cfg: {})
    monkeypatch.setattr("language_router.resolve_turn_language", lambda *a, **k: "en-in")
    monkeypatch.setattr("language_router.apply_language_to_config", lambda cfg, lang: {})

    cfg: dict = {"lang_preset": "tinglish", "llm_max_completion_tokens": 120}
    note_interrupt(cfg, "budget 80 lakhs")
    eng = ConversationEngine(cfg)
    result = asyncio.run(eng.on_user_turn("budget 80 lakhs", turn=3, run_injections=False))
    assert any("INTERRUPT" in m for m in result.system_messages)
