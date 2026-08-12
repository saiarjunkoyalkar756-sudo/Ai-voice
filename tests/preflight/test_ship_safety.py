"""Preflight: no secrets in ship config; template hygiene."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_config_has_no_live_api_keys():
    from ship.secrets import SECRET_CONFIG_KEYS, looks_like_secret_value

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    for key in SECRET_CONFIG_KEYS:
        val = str(cfg.get(key) or "")
        if not val:
            continue
        if "YOUR_" in val or val in (
            "admin",
            "wss://YOUR_PROJECT.livekit.cloud",
            "https://YOUR_PROJECT.supabase.co",
            "YOUR_LIVEKIT_API_KEY",
            "YOUR_LIVEKIT_API_SECRET",
            "YOUR_SUPABASE_ANON_KEY",
        ):
            continue
        # Production template must never embed live keys — use .env / dashboard
        assert not looks_like_secret_value(val), f"config.json may contain secret: {key}"

    # Also scan any *api_key / *secret keys not in the inventory
    for key, raw in cfg.items():
        if not isinstance(raw, str) or not raw:
            continue
        lk = key.lower()
        if any(s in lk for s in ("api_key", "api_secret", "password", "auth_token")):
            if "YOUR_" in raw:
                continue
            assert not looks_like_secret_value(raw), f"config.json leaked {key}"


def test_sanitize_config_strips_keys():
    from ship.secrets import sanitize_config

    dirty = {
        "gemini_api_key": "AIzaSyRealKey1234567890abcd",
        "livekit_api_secret": "secretsecretsecret12",
        "agent_instructions": "You are Arjun",
        "stt_provider": "soniox",
    }
    clean = sanitize_config(dirty)
    assert clean["gemini_api_key"] == ""
    assert clean["livekit_api_secret"] == ""
    assert clean["agent_instructions"] == "You are Arjun"
    assert clean["stt_provider"] == "soniox"


def test_env_example_lists_required_groups():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in (
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "GEMINI_API_KEY",
        "SONIOX_API_KEY",
        "CARTESIA_API_KEY",
        "SUPABASE_URL",
        "JWT_SECRET",
    ):
        assert key in text, f".env.example missing {key}"


def test_gitignore_blocks_env():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi


def test_agent_shim_is_thin():
    lines = (ROOT / "agent.py").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) < 80, "agent.py must stay a thin shim"
    assert "engine.agent_runtime" in (ROOT / "agent.py").read_text()


def test_latency_best_fit_present():
    assert (ROOT / "LATENCY_BEST_FIT_PRODUCTION.md").is_file()
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert float(cfg.get("stt_max_endpointing_delay", 0)) == 0.2
    assert cfg.get("filler_phrases_enabled") is False
    assert int(cfg.get("system_prompt_token_budget") or 0) == 1000
