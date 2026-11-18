"""Preflight: production latency + structure gates."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_latency_best_fit_knobs():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg["stt_provider"] == "soniox"
    assert float(cfg["stt_min_endpointing_delay"]) == 0.2
    assert float(cfg["stt_max_endpointing_delay"]) == 0.2
    assert int(cfg["stt_max_endpoint_delay_ms"]) == 200
    assert cfg["tts_provider"] in ("cartesia", "sarvam")
    assert cfg["cartesia_tts_model"] == "sonic-3.5"
    assert cfg["filler_phrases_enabled"] is False
    assert cfg.get("silence_guard_enabled") is False
    assert int(cfg["system_prompt_token_budget"]) == 1000
    assert int(cfg.get("llm_tiered_hard_cap_ms") or 0) == 3000
    assert cfg["first_tts_chunk_fast_path"] is True
    assert cfg["tts_aggressive_chunking_enabled"] is True
    assert cfg["parallel_turn_injectors_enabled"] is True


def test_ship_production_latency_dict():
    from ship.packager import _PRODUCTION_LATENCY

    assert _PRODUCTION_LATENCY["stt_provider"] == "soniox"
    assert _PRODUCTION_LATENCY["llm_context_prewarm"] is True
    assert _PRODUCTION_LATENCY["speculative_reply_enabled"] is True
    assert _PRODUCTION_LATENCY["filler_phrases_enabled"] is False
    assert float(_PRODUCTION_LATENCY["stt_max_endpointing_delay"]) == 0.2


def test_ttft_policy_matches_best_fit():
    from engine.ttft_policy import apply_ttft_defaults

    p = apply_ttft_defaults({})
    assert p.hard_cap_ms == 3000.0
    assert p.retry_ms == 1500.0


def test_sql_migrations_present():
    sql = ROOT / "sql"
    assert (sql / "supabase_schema.sql").is_file() or list(sql.glob("supabase_migration*.sql"))


def test_requirements_present():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for pkg in ("livekit-agents", "fastapi", "httpx", "python-dotenv"):
        # flexible match
        assert any(pkg.replace("-", "_") in line or pkg in line for line in req.splitlines()) or pkg in req


def test_dockerfile_and_compose():
    assert (ROOT / "Dockerfile").is_file()
    assert (ROOT / "docker-compose.yml").is_file() or (ROOT / "supervisord.conf").is_file()
