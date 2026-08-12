#!/usr/bin/env python3
"""CI gate: fail if real-call latency p50 regresses vs champion baseline."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from turn_latency import check_regression, summarize_turn_latencies


def _load_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return list(data.get("latency_per_interaction") or [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Latency regression gate")
    parser.add_argument(
        "--journal",
        default=str(_ROOT / "data/latency_baselines/real_calls_journal.json"),
        help="Current latency journal JSON",
    )
    parser.add_argument(
        "--baseline",
        default=str(_ROOT / "data/latency_baselines/champion_baseline.json"),
        help="Champion baseline JSON",
    )
    parser.add_argument("--tolerance", type=float, default=0.05, help="Allowed p50/p95 regression")
    args = parser.parse_args()

    journal_path = Path(args.journal)
    baseline_path = Path(args.baseline)
    if not journal_path.is_file():
        print(f"SKIP: no journal at {journal_path}")
        return 0
    if not baseline_path.is_file():
        print(f"SKIP: no baseline at {baseline_path}")
        return 0

    rows = _load_rows(journal_path)
    if not rows:
        print("SKIP: journal has no turns")
        return 0

    current = summarize_turn_latencies(rows)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    result = check_regression(current, baseline, tolerance=args.tolerance)

    print(f"Current p50={current.get('p50_ms')}ms p95={current.get('p95_ms')}ms (n={current.get('count')})")
    for key, check in (result.get("checks") or {}).items():
        status = "PASS" if check.get("pass") else "FAIL"
        print(
            f"  {key}: {check.get('current')} vs baseline {check.get('baseline')} "
            f"(limit {check.get('limit')}) — {status}"
        )

    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())