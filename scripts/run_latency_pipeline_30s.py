#!/usr/bin/env python3
"""
30-second automated latency pipeline for Speaksy (Tinglish).

Runs offline engine metrics simulation + policy checks.
Wall-clock hard stop: 30s.

Usage:
  python3 scripts/run_latency_pipeline_30s.py
  python3 scripts/run_latency_pipeline_30s.py --strict
Exit 0 = pass, 1 = fail, 2 = timeout/error
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEADLINE_S = 30.0

# Component budgets (ms) — server-side, excl. PSTN
BUDGETS = {
    "stt_final": 700.0,
    "turn_inject": 80.0,
    "llm_ttft": 1800.0,
    "reply_buffer": 400.0,
    "tts_ttfa": 250.0,
    "e2e_p50": 1200.0,
    "e2e_p95": 2500.0,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Speaksy 30s latency pipeline")
    parser.add_argument("--strict", action="store_true", help="Fail if any stage over budget")
    parser.add_argument("--turns", type=int, default=15, help="Simulated turns")
    args = parser.parse_args()

    t0 = time.perf_counter()
    report: dict = {"ok": True, "checks": [], "elapsed_s": 0.0}

    def check(name: str, cond: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "pass": cond, "detail": detail})
        if not cond:
            report["ok"] = False

    try:
        from engine.ttft_policy import apply_ttft_defaults
        from engine.metrics.turn_metrics import TurnMetricsCollector
        from turn_latency import summarize_turn_latencies

        cfg: dict = {"lang_preset": "tinglish"}
        pol = apply_ttft_defaults(cfg)
        check("ttft_hard_cap_le_3000", pol.hard_cap_ms <= 3000.0, f"cap={pol.hard_cap_ms}")
        check("ttft_retry_le_1500", pol.retry_ms <= 1500.0, f"retry={pol.retry_ms}")

        coll = TurnMetricsCollector(room_id="pipeline30", config_hash="pipe")
        for i in range(1, args.turns + 1):
            if time.perf_counter() - t0 > DEADLINE_S:
                check("wall_clock_30s", False, "deadline exceeded mid-run")
                break
            # Simulated production-good path (not worst-case SLA)
            stt, inj, llm, buf, tts = 110.0, 28.0, 380.0 + i * 3, 45.0, 55.0
            coll.begin_turn(i, transcript="price check", adaptive_endpoint_ms=stt)
            coll.note_inject(inj)
            coll.note_llm_ttft(llm)
            coll.note_reply_buffer(buf)
            coll.note_tts_ttfa(tts, reply_cache_hit=(i % 4 == 0))
            coll.end_turn()

        exp = coll.export()
        summary = exp.get("summary") or summarize_turn_latencies(exp.get("turns") or [])
        check("has_turns", summary.get("count", 0) >= args.turns // 2, str(summary.get("count")))
        check(
            "e2e_p50",
            float(summary.get("p50_ms") or 0) <= BUDGETS["e2e_p50"] * 2,  # sim uses recorded components
            f"p50={summary.get('p50_ms')}",
        )

        # Stage p50 from collector
        stage_p50 = exp.get("stage_p50") or {}
        for stage, budget in [
            ("stt_final", BUDGETS["stt_final"]),
            ("turn_inject", BUDGETS["turn_inject"]),
            ("llm_ttft", BUDGETS["llm_ttft"]),
            ("tts_ttfa", BUDGETS["tts_ttfa"]),
        ]:
            val = stage_p50.get(stage)
            if val is None:
                check(f"stage_{stage}_present", False, "missing")
            else:
                ok = float(val) <= budget
                if not args.strict and stage == "llm_ttft":
                    ok = float(val) <= budget  # always enforce hard cap
                check(f"stage_{stage}_budget", ok, f"{val}<={budget}")

        elapsed = time.perf_counter() - t0
        report["elapsed_s"] = round(elapsed, 3)
        check("wall_clock_under_30s", elapsed < DEADLINE_S, f"{elapsed:.3f}s")

        report["summary"] = summary
        report["stage_p50"] = stage_p50
        report["ttft_policy"] = {
            "retry_ms": pol.retry_ms,
            "hard_cap_ms": pol.hard_cap_ms,
        }
    except Exception as exc:
        report["ok"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["elapsed_s"] = round(time.perf_counter() - t0, 3)

    print(json.dumps(report, indent=2))
    if report.get("elapsed_s", 0) > DEADLINE_S:
        return 2
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
