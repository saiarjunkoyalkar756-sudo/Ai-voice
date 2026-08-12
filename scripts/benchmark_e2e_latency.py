#!/usr/bin/env python3
"""
Benchmark STT-final → first TTS audio latency (P2.12 / Operation Sub-Second Phase 0).

Modes:
  --simulate       Synthetic turns using CallQualityScorer timing model (default)
  --journal PATH   Read latency_per_interaction from a saved JSON export
  --from-supabase  Pull last N call_logs from Supabase (real calls)

Targets: p50 < 700ms, p95 < 1100ms (server-side TTFA).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from turn_latency import (
    P50_TARGET_MS,
    P95_TARGET_MS,
    check_regression,
    reply_cache_metrics,
    summarize_turn_latencies,
)


def _simulate_turns(n: int, *, seed: int = 42) -> list[dict]:
    """Realistic synthetic per-turn latency rows (ms) — models Tinglish @ 350ms endpoint."""
    random.seed(seed)
    rows: list[dict] = []

    for _ in range(n):
        endpointing = max(280.0, random.gauss(350, 40))
        stt_proc = max(40.0, random.gauss(75, 20))
        llm = max(120.0, random.gauss(260, 85))
        buffer_ms = max(8.0, random.gauss(30, 12))
        tts = max(45.0, random.gauss(115, 35))
        ttfa = endpointing + stt_proc + llm + buffer_ms + tts
        rows.append({
            "endpointing_ms": round(endpointing, 1),
            "stt_ms": round(stt_proc, 1),
            "llm_ms": round(llm, 1),
            "buffer_ms": round(buffer_ms, 1),
            "tts_ms": round(tts, 1),
            "ttfa_server_ms": round(ttfa, 1),
            "e2e_ms": round(ttfa, 1),
        })

    return rows


def _extract_latency_rows(extracted_info: dict | None) -> list[dict]:
    """Flatten latency_per_interaction from any export shape."""
    if not isinstance(extracted_info, dict):
        return []
    for getter in (
        lambda: extracted_info.get("latency_per_interaction"),
        lambda: (extracted_info.get("latency_journal") or {}).get("latency_per_interaction"),
        lambda: ((extracted_info.get("quality_scores") or {}).get("metrics") or {}).get(
            "latency_per_interaction"
        ),
    ):
        rows = getter()
        if rows:
            return list(rows)
    return []


def _load_journal(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return (
            data.get("latency_per_interaction")
            or data.get("interaction_latencies")
            or _extract_latency_rows(data)
            or []
        )
    return []


async def _fetch_supabase_rows(limit: int) -> tuple[list[dict], dict]:
    from db import get_supabase

    sb = await get_supabase()
    if not sb:
        return [], {"error": "Supabase not configured"}

    res = (
        sb.table("call_logs")
        .select("id,created_at,extracted_info")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    all_rows: list[dict] = []
    calls_with = 0
    for log in res.data or []:
        lat = _extract_latency_rows(log.get("extracted_info") or {})
        if not lat:
            continue
        calls_with += 1
        for row in lat:
            enriched = dict(row)
            enriched["_call_id"] = log.get("id")
            enriched["_created_at"] = log.get("created_at")
            all_rows.append(enriched)

    meta = {
        "source": "supabase",
        "calls_scanned": len(res.data or []),
        "calls_with_latency": calls_with,
        "turn_count": len(all_rows),
    }
    return all_rows, meta


def _load_baseline(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _print_report(summary: dict) -> None:
    print("\nSTT-final → first TTS audio")
    print(f"  samples : {summary['count']}")
    print(f"  p50     : {summary['p50_ms']} ms  (target ≤ {P50_TARGET_MS})")
    print(f"  p95     : {summary['p95_ms']} ms  (target ≤ {P95_TARGET_MS})")
    print(f"  p99     : {summary['p99_ms']} ms")
    print(f"  max     : {summary['max_ms']} ms")
    if summary.get("stt_p50_ms") is not None:
        print(f"  stt p50 : {summary['stt_p50_ms']} ms")
    if summary.get("llm_p50_ms") is not None:
        print(f"  llm p50 : {summary['llm_p50_ms']} ms")
    if summary.get("tts_p50_ms") is not None:
        print(f"  tts p50 : {summary['tts_p50_ms']} ms")

    ok_p50 = summary.get("meets_p50_target")
    ok_p95 = summary.get("meets_p95_target")
    if ok_p50 is not None:
        print(f"\n  p50 target : {'PASS' if ok_p50 else 'MISS'}")
    if ok_p95 is not None:
        print(f"  p95 target : {'PASS' if ok_p95 else 'MISS'}")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return round(ordered[idx], 1)


def _stage_histogram(rows: list[dict]) -> None:
    stages = [
        "endpointing_ms",
        "stt_ms",
        "llm_ms",
        "buffer_ms",
        "tts_ms",
        "ttfa_server_ms",
        "ttfa_estimated_ms",
    ]
    print("\nPer-stage histogram (ms)")
    print(f"  {'stage':<22} {'n':>5} {'p50':>8} {'p95':>8} {'max':>8}")
    for key in stages:
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        if not vals:
            continue
        print(
            f"  {key:<22} {len(vals):>5} {_percentile(vals, 50):>8.1f} "
            f"{_percentile(vals, 95):>8.1f} {max(vals):>8.1f}"
        )


def _phase0_questions(rows: list[dict]) -> None:
    llm = [float(r["llm_ms"]) for r in rows if r.get("llm_ms") is not None]
    buf = [float(r["buffer_ms"]) for r in rows if r.get("buffer_ms") is not None]
    ttfa = [float(r["ttfa_server_ms"]) for r in rows if r.get("ttfa_server_ms") is not None]

    print("\nPhase 0 gate questions")
    if llm:
        cb_riders = sum(1 for x in llm if x >= 2900)
        print(
            f"  1. llm_ms >= 2900 (CB ceiling riders): "
            f"{cb_riders}/{len(llm)} = {100 * cb_riders / len(llm):.1f}%"
        )
        print(f"     llm p50={_percentile(llm, 50):.0f}ms  p95={_percentile(llm, 95):.0f}ms")
    else:
        print("  1. llm_ms: no samples")

    cache = reply_cache_metrics(rows)
    print(
        f"  2. Reply cache hit rate: {cache['hits']}/{cache['lookups']} "
        f"({cache['hit_rate']:.1%})"
    )

    if ttfa and llm:
        ttfa_p50 = _percentile(ttfa, 50)
        llm_p50 = _percentile(llm, 50)
        tail = _percentile(ttfa, 95) - _percentile(ttfa, 50)
        kind = "p95-tail" if tail > 1500 else "p50-systemic"
        print(f"  3. Problem shape: {kind} (ttfa p50={ttfa_p50:.0f}, p95-p50 gap={tail:.0f})")
        if llm_p50 >= 600:
            print("     → Phase 2 (prompt/cache) stays HIGH priority")
        else:
            print("     → Phase 2 demotes; Phase 3 promotes")

    pairs = [
        (float(r["llm_ms"]), float(r["buffer_ms"]))
        for r in rows
        if r.get("llm_ms") is not None and r.get("buffer_ms") is not None
    ]
    if len(pairs) >= 3:
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        mx = statistics.mean(xs)
        my = statistics.mean(ys)
        num = sum((x - mx) * (y - my) for x, y in pairs)
        den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
        corr = num / den if den else 0.0
        buf_p95 = _percentile(ys, 95)
        print(
            f"  4. buffer_ms vs llm_ms correlation: r={corr:.3f} "
            f"(buffer p95={buf_p95:.0f}ms, n={len(pairs)})"
        )
        if buf_p95 < 100:
            print("     → Buffer is NOT stacking with slow LLM; stop tuning chunking")
    else:
        print("  4. buffer/llm correlation: insufficient paired samples")


def _print_cache_metrics(rows: list[dict]) -> None:
    cache = reply_cache_metrics(rows)
    if cache["lookups"]:
        print(f"\nReply cache: {cache['hits']}/{cache['lookups']} hits ({cache['hit_rate']:.1%})")


def _print_regression(regression: dict) -> None:
    print("\nBaseline regression check")
    for key, check in (regression.get("checks") or {}).items():
        status = "PASS" if check.get("pass") else "FAIL"
        print(
            f"  {key}: {check.get('current')} ms vs baseline {check.get('baseline')} ms "
            f"(limit {check.get('limit')}) — {status}"
        )
    overall = "PASS" if regression.get("pass") else "FAIL"
    print(f"  overall: {overall}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark E2E turn latency")
    parser.add_argument("--simulate", action="store_true", help="Run synthetic benchmark")
    parser.add_argument("--turns", type=int, default=200, help="Simulated turn count")
    parser.add_argument("--journal", type=str, default="", help="Path to latency JSON export")
    parser.add_argument(
        "--from-supabase",
        action="store_true",
        help="Pull real call_logs latency from Supabase",
    )
    parser.add_argument(
        "--calls",
        type=int,
        default=100,
        help="Max call_logs rows to scan with --from-supabase",
    )
    parser.add_argument(
        "--export",
        type=str,
        default="",
        help="Write fetched/analyzed rows to JSON path",
    )
    parser.add_argument(
        "--phase0",
        action="store_true",
        help="Print Phase 0 gate report (histogram + 4 questions)",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default="",
        help="Baseline JSON for regression check (5%% tolerance on p50/p95)",
    )
    parser.add_argument(
        "--write-baseline",
        type=str,
        default="",
        help="Write current summary to baseline JSON path",
    )
    args = parser.parse_args()

    meta: dict = {}
    if args.from_supabase:
        rows, meta = asyncio.run(_fetch_supabase_rows(args.calls))
        print(
            f"Supabase: scanned {meta.get('calls_scanned', 0)} calls, "
            f"{meta.get('calls_with_latency', 0)} with latency, {len(rows)} turns"
        )
    elif args.journal:
        rows = _load_journal(args.journal)
        print(f"Loaded {len(rows)} turns from {args.journal}")
    else:
        print(f"Simulating {args.turns} turns…")
        rows = _simulate_turns(args.turns)

    if not rows:
        print("No latency rows to analyze.")
        return 1

    summary = summarize_turn_latencies(rows)
    _print_report(summary)
    if args.phase0 or args.from_supabase:
        _stage_histogram(rows)
        _phase0_questions(rows)
    _print_cache_metrics(rows)

    export_path = args.export or (
        "data/latency_baselines/real_calls_journal.json" if args.from_supabase else ""
    )
    if export_path:
        payload = {**meta, "latency_per_interaction": rows, "summary": summary}
        os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\nExported → {export_path}")

    if args.write_baseline:
        payload = {
            "source": "journal" if args.journal else "synthetic",
            "turns": len(rows),
            "summary": summary,
            "reply_cache_metrics": reply_cache_metrics(rows),
        }
        out_path = args.write_baseline
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\nWrote baseline → {out_path}")

    exit_code = 0
    if args.baseline:
        baseline = _load_baseline(args.baseline)
        regression = check_regression(summary, baseline)
        _print_regression(regression)
        if not regression.get("pass"):
            exit_code = 3

    if summary.get("meets_p95_target") is False:
        exit_code = max(exit_code, 2)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())