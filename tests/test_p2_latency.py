"""P2 latency layer — reply prebake, turn latency stats, speculative metrics."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from greeting_cache import TINGLISH_REPLY_VARIANTS, reply_variants_for_preset
from speculative_reply import get_speculative_metrics, record_barge_in
from turn_latency import (
    P50_TARGET_MS,
    P95_TARGET_MS,
    build_latency_export,
    check_regression,
    reply_cache_metrics,
    summarize_turn_latencies,
)


def test_reply_variants_count():
    from preset_contract import min_reply_variants_for_preset

    variants = reply_variants_for_preset("tinglish")
    assert len(variants) >= min_reply_variants_for_preset("tinglish")
    assert len(TINGLISH_REPLY_VARIANTS) >= 20


def test_turn_latency_targets():
    rows = [
        {"ttfa_server_ms": 520},
        {"ttfa_server_ms": 680},
        {"ttfa_server_ms": 890},
        {"ttfa_server_ms": 1050},
    ]
    summary = summarize_turn_latencies(rows)
    assert summary["count"] == 4
    assert summary["p50_ms"] == 890
    assert summary["targets"]["p50_ms"] == P50_TARGET_MS
    assert summary["targets"]["p95_ms"] == P95_TARGET_MS


def test_quality_scorer_reply_cache_hit():
    from call_quality_scorer import CallQualityScorer

    qs = CallQualityScorer()
    qs.metrics._pending_ttfa_start_ts = 0.0
    qs.metrics._pending_stt_final_ts = 0.1
    qs.metrics._pending_turn_completed_ts = 0.15
    qs.metrics._pending_llm_ts = 0.4
    qs.record_tts_latency(8.5, reply_cache_hit=True)
    row = qs.metrics.interaction_latencies[0]
    assert row["reply_cache_hit"] is True
    assert qs.metrics.reply_cache_hits == 1
    assert qs.metrics.reply_cache_lookups == 1


def test_reply_cache_metrics():
    rows = [
        {"tts_ms": 12.0, "reply_cache_hit": True},
        {"tts_ms": 95.0, "reply_cache_hit": False},
        {"tts_ms": 88.0, "reply_cache_hit": True},
    ]
    m = reply_cache_metrics(rows)
    assert m["lookups"] == 3
    assert m["hits"] == 2
    assert m["hit_rate"] == round(2 / 3, 3)


def test_build_latency_export():
    payload = {
        "metrics": {
            "latency_per_interaction": [
                {
                    "turn": 1,
                    "ttfa_server_ms": 620.0,
                    "tts_ms": 15.0,
                    "reply_cache_hit": True,
                }
            ],
            "reply_cache_metrics": {"lookups": 1, "hits": 1, "hit_rate": 1.0},
        }
    }
    export = build_latency_export(
        payload,
        live_config={
            "lang_preset": "tinglish",
            "_llm_prewarm_ttft_ms": 180.0,
            "_llm_prewarm_ready": True,
        },
    )
    assert len(export["latency_per_interaction"]) == 1
    assert export["summary"]["count"] == 1
    assert export["reply_cache_metrics"]["hits"] == 1
    assert export["preset_id"] == "tinglish"
    assert export["telemetry"]["llm_prewarm_ttft_ms"] == 180.0


def test_baseline_regression_pass_and_fail():
    baseline = {"summary": {"p50_ms": 700.0, "p95_ms": 1000.0}}
    ok = check_regression({"p50_ms": 720.0, "p95_ms": 1040.0}, baseline)
    assert ok["pass"] is True
    bad = check_regression({"p50_ms": 800.0, "p95_ms": 1040.0}, baseline)
    assert bad["pass"] is False


def test_speculative_barge_in_metrics():
    cfg: dict = {"speculative_reply_enabled": True}
    record_barge_in(cfg, word_count=1, agent_was_speaking=True, min_words=2)
    record_barge_in(cfg, word_count=4, agent_was_speaking=True, min_words=2)
    m = get_speculative_metrics(cfg)
    assert m["barge_in_total"] == 2
    assert m["barge_in_false_positive"] == 1
    assert m["barge_in_false_positive_rate"] == 0.5