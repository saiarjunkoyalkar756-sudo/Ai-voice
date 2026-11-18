#!/usr/bin/env python3
"""
Production preflight — run BEFORE starting the agent for any client ship.

  python3 scripts/run_preflight.py
  python3 scripts/run_preflight.py --strict
  python3 scripts/run_preflight.py --secrets-only
  python3 scripts/run_preflight.py --json

Exit 0 = safe to start · 1 = failures · 2 = critical (secrets missing)
"""
from __future__ import annotations

import argparse
import json
import os
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Voicely production preflight")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    parser.add_argument("--json", action="store_true", help="Machine-readable report")
    parser.add_argument(
        "--secrets-only",
        action="store_true",
        help="Only check required env secrets (fast gate)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run broader offline unit suites (latency, golden, engine)",
    )
    args = parser.parse_args()

    # Always run critical secret checks first
    secret_code = _check_secrets(as_json=False if not args.secrets_only else args.json)
    if args.secrets_only:
        return secret_code
    if secret_code != 0:
        if not args.json:
            print("\n✗ PREFLIGHT FAILED — missing required secrets (fill .env or dashboard)")
        return 2

    try:
        import pytest
    except ImportError:
        return _inline_checks(strict=args.strict, as_json=args.json)

    suites = [str(ROOT / "tests" / "preflight")]
    code = pytest.main([
        *suites,
        "-q",
        "--tb=line",
        f"--rootdir={ROOT}",
    ])

    code2 = 0
    if args.full:
        code2 = pytest.main([
            str(ROOT / "tests" / "test_latency_pipeline_30s.py"),
            str(ROOT / "tests" / "test_engine_foundation.py"),
            str(ROOT / "tests" / "test_engine_complete.py"),
            str(ROOT / "tests" / "test_tinglish_eval_suite.py"),
            str(ROOT / "tests" / "test_golden_calls.py"),
            str(ROOT / "tests" / "test_tts_normalizer_golden.py"),
            str(ROOT / "tests" / "test_preset_contract.py"),
            str(ROOT / "tests" / "test_reply_cache.py"),
            str(ROOT / "tests" / "test_llm_tiered_guard.py"),
            str(ROOT / "tests" / "test_kb_compiler.py"),
            "-q",
            "--tb=line",
            f"--rootdir={ROOT}",
        ])

    overall = 0 if (code == 0 and code2 == 0) else 1

    if args.json:
        print(json.dumps({"ok": overall == 0, "pytest_exit": overall, "secrets_ok": True}))
    else:
        if overall == 0:
            print("\n✓ PREFLIGHT PASSED — safe to start agent + ui_server")
            print("  next: python3 agent.py start")
            print("        uvicorn ui_server:app --host 0.0.0.0 --port 8000")
        else:
            print("\n✗ PREFLIGHT FAILED — do not ship / do not start agent")
    return overall


def _check_secrets(*, as_json: bool) -> int:
    from ship.secrets import REQUIRED_ENV_FOR_START

    missing = [k for k in REQUIRED_ENV_FOR_START if not os.getenv(k, "").strip()]
    # Allow non-prod local if DISABLE_AUTH and partial — still report
    if as_json:
        print(json.dumps({"ok": not missing, "missing": missing}))
    else:
        if missing:
            print("Missing required env (set in .env or Dashboard → API Settings):")
            for k in missing:
                print(f"  ✗ {k}")
        else:
            print("✓ All required secrets present in environment")
    return 0 if not missing else 2


def _inline_checks(*, strict: bool, as_json: bool) -> int:
    from ship.secrets import REQUIRED_ENV_FOR_START

    checks = []
    ok = True

    def add(name: str, passed: bool, detail: str = "", critical: bool = False):
        nonlocal ok
        checks.append({"name": name, "pass": passed, "detail": detail, "critical": critical})
        if not passed and (critical or strict):
            ok = False

    for key in REQUIRED_ENV_FOR_START:
        add(key, bool(os.getenv(key, "").strip()), critical=True)

    add("config.json", (ROOT / "config.json").is_file(), critical=True)
    add("agent.py", (ROOT / "agent.py").is_file(), critical=True)
    add(
        "engine/agent_runtime.py",
        (ROOT / "engine" / "agent_runtime.py").is_file(),
        critical=True,
    )

    try:
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        for secret in ("gemini_api_key", "livekit_api_key", "cartesia_api_key"):
            val = str(cfg.get(secret) or "")
            add(
                f"config_no_embedded_{secret}",
                (not val) or "YOUR_" in val,
                detail="must be empty — secrets in .env only",
                critical=True,
            )
        add("stt_soniox", cfg.get("stt_provider") == "soniox")
        add("endpointing_0.2", float(cfg.get("stt_max_endpointing_delay") or 0) == 0.2)
        add("filler_off", cfg.get("filler_phrases_enabled") is False)
        add("prompt_budget_1000", int(cfg.get("system_prompt_token_budget") or 0) == 1000)
    except Exception as exc:
        add("config_parse", False, str(exc), critical=True)

    for mod in ("engine", "call_quality_scorer", "stt_provider", "token_counter", "ship.packager"):
        try:
            __import__(mod)
            add(f"import_{mod}", True)
        except Exception as exc:
            add(f"import_{mod}", False, str(exc), critical=True)

    if as_json:
        print(json.dumps({"ok": ok, "checks": checks}, indent=2))
    else:
        for c in checks:
            mark = "✓" if c["pass"] else "✗"
            print(f"  {mark} {c['name']}" + (f" — {c['detail']}" if c["detail"] else ""))
        print("\n✓ PREFLIGHT PASSED" if ok else "\n✗ PREFLIGHT FAILED")
    return 0 if ok else (
        2 if any(not c["pass"] and c.get("critical") for c in checks) else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
