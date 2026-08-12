#!/usr/bin/env python3
"""
Client bootstrap after unpacking a Speaksy ship ZIP.

  1. Load .env
  2. Validate required secrets
  3. Pre-warm first dialogue + greeting/session PCM
  4. Preload knowledge packs + IQ registry (via worker_prewarm)
  5. Run preflight suite

Usage:
  python3 scripts/bootstrap_client.py
  python3 scripts/bootstrap_client.py --skip-preflight
  python3 scripts/bootstrap_client.py --prewarm-only
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


async def _prewarm() -> int:
    from worker_prewarm import invalidate_worker_prewarm, run_worker_prewarm

    invalidate_worker_prewarm()
    await run_worker_prewarm()
    cache = ROOT / "data" / "greeting_pcm_cache"
    pcm = list(cache.glob("*.pcm")) if cache.is_dir() else []
    print(f"✓ Prewarm complete — {len(pcm)} PCM file(s) in data/greeting_pcm_cache/")
    if not pcm:
        print(
            "  ⚠ No PCM on disk. Check CARTESIA_API_KEY (or TTS provider key) "
            "and first_line in config.json"
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Speaksy client bootstrap")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--prewarm-only", action="store_true")
    args = parser.parse_args()

    from ship.secrets import REQUIRED_ENV_FOR_START

    missing = [k for k in REQUIRED_ENV_FOR_START if not os.getenv(k, "").strip()]
    if missing:
        print("Missing required secrets (fill .env or Dashboard → API Settings):")
        for k in missing:
            print(f"  ✗ {k}")
        if args.prewarm_only:
            return 2
        # still allow preflight structure tests? no — secrets required for bootstrap
        return 2

    prewarm_code = asyncio.run(_prewarm())
    if args.prewarm_only:
        return prewarm_code

    if args.skip_preflight:
        print("Skipping preflight (--skip-preflight)")
        return prewarm_code

    r = subprocess.call([sys.executable, str(ROOT / "scripts" / "run_preflight.py")])
    if r != 0:
        return r
    if prewarm_code != 0:
        print("⚠ Preflight OK but prewarm had issues — first call may be slightly colder")
        return 0
    print("\n✓ Bootstrap complete — safe to start agent + ui_server")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
