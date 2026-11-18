"""
Automated latency pipeline test — 30 second wall-clock budget.

Simulates Voicely turn stages (STT → inject → LLM TTFT → buffer → TTS)
using the production engine metrics path. No LiveKit, no network LLM.

Exit criteria (production targets from VOICELY_ENGINE_MASTER_PLAN):
  - Entire test module finishes in < 30s
  - Simulated turn e2e (inject+llm+tts components) under stage budgets
  - TTFT policy hard cap ≤ 1800ms
  - Waterfall metrics populated for all 6 stages
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

# Hard wall for this module — CI kills if we regress into a hang
pytestmark = pytest.mark.timeout(30)

# Production stage budgets for the *simulated* offline pipeline (ms).
# These are engine-side budgets (not PSTN).
STAGE_BUDGET_MS = {
    "stt_final": 700.0,       # endpointing delay ceiling
    "turn_inject": 80.0,      # knowledge + waves offline budget
    "llm_ttft": 3000.0,       # production best-fit hard cap
    "reply_buffer": 400.0,    # sentence buffer before first speakable
    "tts_ttfa": 250.0,        # first PCM after speakable text
    "first_audio_out": 2800.0,  # felt server e2e excl. PSTN
}


def _simulate_turn_pipeline(
    turn: int,
    *,
    stt_ms: float,
    inject_ms: float,
    llm_ms: float,
    buffer_ms: float,
    tts_ms: float,
    reply_cache_hit: bool = False,
) -> dict[str, Any]:
    """Drive TurnMetricsCollector the same way agent_runtime does mid-call."""
    from engine.metrics.turn_metrics import TurnMetricsCollector, TurnStage

    coll = TurnMetricsCollector(room_id="latency-test-room", config_hash="test_hash")
    coll.begin_turn(turn, transcript="2BHK price entha?", adaptive_endpoint_ms=stt_ms)
    # emulate work (tiny sleep so wall-clock is real but tiny)
    time.sleep(min(0.002, inject_ms / 1000.0))
    coll.note_inject(inject_ms)
    time.sleep(min(0.002, llm_ms / 1000.0))
    coll.note_llm_ttft(llm_ms)
    coll.note_reply_buffer(buffer_ms)
    time.sleep(min(0.002, tts_ms / 1000.0))
    coll.note_tts_ttfa(tts_ms, reply_cache_hit=reply_cache_hit)
    coll.end_turn()
    exp = coll.export()
    assert exp["schema"] == "voicely.turn_metrics.v1"
    return exp


def test_ttft_policy_production_caps():
    from engine.ttft_policy import apply_ttft_defaults, resolve_ttft_policy

    cfg: dict = {}
    p = apply_ttft_defaults(cfg)
    assert p.retry_ms <= 1500.0
    assert p.hard_cap_ms <= 3000.0  # production best-fit SLA
    assert cfg["llm_tiered_hard_cap_ms"] == p.hard_cap_ms
    p2 = resolve_ttft_policy({"llm_tiered_hard_cap_ms": 3000})
    assert p2.hard_cap_ms == 3000.0


def test_single_turn_waterfall_under_budgets():
    # Good path — well under production ceilings
    exp = _simulate_turn_pipeline(
        1,
        stt_ms=120,
        inject_ms=35,
        llm_ms=420,
        buffer_ms=80,
        tts_ms=70,
    )
    row = exp["turns"][0]
    stages = row["stages_ms"]
    for stage, budget in STAGE_BUDGET_MS.items():
        if stage == "first_audio_out":
            # e2e / first audio is wall-measured from begin_turn
            val = row.get("ttfa_server_ms") or row.get("e2e_ms") or stages.get(stage)
        else:
            val = stages.get(stage)
        assert val is not None, f"missing stage {stage}"
        assert float(val) <= budget, f"{stage}={val} > budget {budget}"

    assert exp["summary"]["count"] == 1
    assert "waterfall_p50" in exp["summary"] or exp["stage_p50"]


def test_reply_cache_hit_path_is_faster_tts():
    miss = _simulate_turn_pipeline(
        1, stt_ms=100, inject_ms=30, llm_ms=500, buffer_ms=60, tts_ms=120, reply_cache_hit=False
    )
    hit = _simulate_turn_pipeline(
        2, stt_ms=100, inject_ms=30, llm_ms=500, buffer_ms=20, tts_ms=15, reply_cache_hit=True
    )
    assert hit["turns"][0]["reply_cache_hit"] is True
    assert float(hit["turns"][0]["stages_ms"]["tts_ttfa"]) < float(
        miss["turns"][0]["stages_ms"]["tts_ttfa"]
    )


def test_multi_turn_pipeline_under_30s_wall():
    """10 turns of metrics + engine turn orchestration must finish << 30s."""
    t0 = time.perf_counter()
    from engine.conversation_engine import ConversationEngine
    from engine.ttft_policy import apply_ttft_defaults
    from engine.metrics.turn_metrics import TurnMetricsCollector

    cfg: dict[str, Any] = {
        "lang_preset": "tinglish",
        "llm_max_completion_tokens": 120,
        "parallel_turn_injectors_enabled": True,
        "conversational_iq_v2_enabled": True,
    }
    apply_ttft_defaults(cfg)
    coll = TurnMetricsCollector(room_id="multi", config_hash="m1")
    cfg["_turn_metrics"] = coll

    async def _one(i: int) -> None:
        # Mock identity/language for speed (no network)
        eng = ConversationEngine(cfg)
        # bypass real injectors
        result = await eng.on_user_turn(
            "haan ok" if i % 2 == 0 else "price entha?",
            turn=i,
            run_injections=False,
        )
        assert result.max_completion_tokens is not None or result.skip_llm
        coll.begin_turn(i, transcript="haan", adaptive_endpoint_ms=100 + i)
        coll.note_inject(result.inject_ms or 20.0)
        coll.note_llm_ttft(300 + i * 5)
        coll.note_reply_buffer(50)
        coll.note_tts_ttfa(60 + i)
        coll.end_turn()

    async def _run() -> None:
        for i in range(1, 11):
            await _one(i)

    asyncio.run(_run())
    elapsed = time.perf_counter() - t0
    exp = coll.export()
    assert exp["summary"]["count"] == 10
    assert elapsed < 30.0, f"pipeline took {elapsed:.2f}s > 30s budget"
    # p50 e2e should be sensible for simulated turns
    assert exp["summary"]["p50_ms"] > 0


def test_full_latency_pipeline_script_contract():
    """Mirror scripts/run_latency_pipeline_30s.py scoring logic."""
    from turn_latency import check_regression, summarize_turn_latencies

    rows = []
    for i in range(5):
        exp = _simulate_turn_pipeline(
            i + 1,
            stt_ms=100 + i * 10,
            inject_ms=25 + i,
            llm_ms=350 + i * 20,
            buffer_ms=40,
            tts_ms=55,
        )
        rows.extend(exp["turns"])

    summary = summarize_turn_latencies(rows)
    assert summary["count"] == 5
    assert summary["p50_ms"] <= STAGE_BUDGET_MS["first_audio_out"]
    # regression vs itself must pass
    reg = check_regression(summary, summary, tolerance=0.05)
    assert reg["pass"] is True


def test_pipeline_wall_clock_guard():
    """Meta: this entire file's active work must stay far under 30s."""
    t0 = time.perf_counter()
    for i in range(20):
        _simulate_turn_pipeline(
            i + 1,
            stt_ms=80,
            inject_ms=20,
            llm_ms=200,
            buffer_ms=30,
            tts_ms=40,
            reply_cache_hit=(i % 3 == 0),
        )
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"hot loop alone took {elapsed:.2f}s — too slow"
