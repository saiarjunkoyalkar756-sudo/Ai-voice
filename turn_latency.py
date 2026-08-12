"""
Turn latency analytics — STT-final → first TTS audio (voice-to-voice TTFA).

Targets (P2.12): p50 < 700ms, p95 < 1100ms server-side.
"""
from __future__ import annotations

from typing import Any

P50_TARGET_MS = 700.0
P95_TARGET_MS = 1100.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return round(ordered[idx], 1)


def stt_final_to_tts_ms(row: dict[str, Any]) -> float | None:
    """Extract STT-final → first TTS audio ms from a per-turn latency row."""
    for key in ("ttfa_server_ms", "e2e_ms"):
        val = row.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    stt = row.get("stt_ms")
    llm = row.get("llm_ms")
    buf = row.get("buffer_ms") or 0
    tts = row.get("tts_ms")
    if stt is not None and llm is not None and tts is not None:
        try:
            return float(stt) + float(llm) + float(buf) + float(tts)
        except (TypeError, ValueError):
            pass
    return None


def _vals(rows: list[dict[str, Any]], *keys: str) -> list[float]:
    out: list[float] = []
    for r in rows:
        stages = r.get("stages_ms") or {}
        for k in keys:
            v = r.get(k)
            if v is None and isinstance(stages, dict):
                v = stages.get(k)
            if v is not None:
                try:
                    out.append(float(v))
                    break
                except (TypeError, ValueError):
                    pass
    return out


def summarize_turn_latencies(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate p50/p95 for STT-final → TTS and component breakdown (waterfall)."""
    samples = [v for v in (stt_final_to_tts_ms(r) for r in rows) if v is not None]
    stt_vals = _vals(rows, "stt_ms", "stt_final")
    inject_vals = _vals(rows, "inject_ms", "turn_inject")
    llm_vals = _vals(rows, "llm_ms", "llm_ttft")
    buf_vals = _vals(rows, "buffer_ms", "reply_buffer")
    tts_vals = _vals(rows, "tts_ms", "tts_ttfa")

    result: dict[str, Any] = {
        "count": len(samples),
        "p50_ms": _percentile(samples, 50),
        "p95_ms": _percentile(samples, 95),
        "p99_ms": _percentile(samples, 99),
        "max_ms": round(max(samples), 1) if samples else 0.0,
        "meets_p50_target": _percentile(samples, 50) <= P50_TARGET_MS if samples else None,
        "meets_p95_target": _percentile(samples, 95) <= P95_TARGET_MS if samples else None,
        "targets": {"p50_ms": P50_TARGET_MS, "p95_ms": P95_TARGET_MS},
        "waterfall_p50": {},
        "waterfall_p95": {},
    }
    for name, vals in (
        ("stt_final", stt_vals),
        ("turn_inject", inject_vals),
        ("llm_ttft", llm_vals),
        ("reply_buffer", buf_vals),
        ("tts_ttfa", tts_vals),
    ):
        if vals:
            result["waterfall_p50"][name] = _percentile(vals, 50)
            result["waterfall_p95"][name] = _percentile(vals, 95)
    if stt_vals:
        result["stt_p50_ms"] = _percentile(stt_vals, 50)
    if llm_vals:
        result["llm_p50_ms"] = _percentile(llm_vals, 50)
    if tts_vals:
        result["tts_p50_ms"] = _percentile(tts_vals, 50)
    if inject_vals:
        result["inject_p50_ms"] = _percentile(inject_vals, 50)
    if buf_vals:
        result["buffer_p50_ms"] = _percentile(buf_vals, 50)
    return result


def reply_cache_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate reply PCM cache hit rate from per-turn latency rows."""
    lookups = sum(1 for r in rows if r.get("tts_ms") is not None)
    hits = sum(1 for r in rows if r.get("reply_cache_hit"))
    rate = round(hits / lookups, 3) if lookups else 0.0
    return {
        "lookups": lookups,
        "hits": hits,
        "hit_rate": rate,
    }


def _speculative_partial_telemetry(live_config: dict[str, Any] | None) -> dict[str, Any]:
    try:
        from partial_turn_tracker import get_speculative_partial_metrics

        return get_speculative_partial_metrics(live_config)
    except Exception:
        return {}


def build_latency_export(
    quality_payload: dict[str, Any],
    *,
    live_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Post-call latency journal for Supabase export and benchmark --journal."""
    metrics = quality_payload.get("metrics") or {}
    rows = list(metrics.get("latency_per_interaction") or [])
    summary = summarize_turn_latencies(rows)
    cache = reply_cache_metrics(rows)

    preset_id = ""
    knowledge_pack_id = ""
    if live_config:
        try:
            from language_router import resolve_lang_preset
            from preset_contract import knowledge_pack_id_for

            preset_id = resolve_lang_preset(live_config.get("lang_preset"), live_config)
            knowledge_pack_id = knowledge_pack_id_for(preset_id)
        except Exception:
            preset_id = str(live_config.get("lang_preset") or "")

    return {
        "preset_id": preset_id,
        "knowledge_pack_id": knowledge_pack_id,
        "latency_per_interaction": rows,
        "summary": summary,
        "reply_cache_metrics": cache,
        "telemetry": {
            "llm_prewarm_ttft_ms": (live_config or {}).get("_llm_prewarm_ttft_ms"),
            "llm_prewarm_ready": bool((live_config or {}).get("_llm_prewarm_ready")),
            "stt_adaptive_endpoint_enabled": bool(
                (live_config or {}).get("stt_adaptive_endpoint_enabled")
            ),
            "tts_aggressive_chunking_enabled": bool(
                (live_config or {}).get("tts_aggressive_chunking_enabled")
            ),
            "speculative_partial": _speculative_partial_telemetry(live_config),
        },
    }


REGRESSION_TOLERANCE = 0.05


def check_regression(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    tolerance: float = REGRESSION_TOLERANCE,
) -> dict[str, Any]:
    """Return pass/fail if current p50/p95 regressed more than tolerance vs baseline."""
    cur = current if "p50_ms" in current else current.get("summary") or {}
    base = baseline if "p50_ms" in baseline else baseline.get("summary") or {}

    results: dict[str, Any] = {"tolerance": tolerance, "checks": {}}
    ok = True
    for key in ("p50_ms", "p95_ms"):
        cur_val = cur.get(key)
        base_val = base.get(key)
        if cur_val is None or base_val is None:
            continue
        limit = float(base_val) * (1.0 + tolerance)
        passed = float(cur_val) <= limit
        results["checks"][key] = {
            "current": cur_val,
            "baseline": base_val,
            "limit": round(limit, 1),
            "pass": passed,
        }
        if not passed:
            ok = False
    results["pass"] = ok
    return results