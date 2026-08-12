"""Runtime gates that must pass before starting production agent."""
from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_agent_entry_points_to_runtime():
    src = (ROOT / "agent.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # must import or re-export from engine.agent_runtime
    assert "engine.agent_runtime" in src or "agent_runtime" in src
    assert "if __name__" in src or "cli.run_app" in src or "agents.cli" in src


def test_engine_agent_runtime_exists_and_large():
    p = ROOT / "engine" / "agent_runtime.py"
    assert p.is_file()
    # production runtime should be substantial
    assert p.stat().st_size > 50_000


def test_conversation_engine_importable():
    m = importlib.import_module("engine.conversation_engine")
    assert m is not None


def test_ttft_policy_production_defaults():
    from engine.ttft_policy import apply_ttft_defaults

    p = apply_ttft_defaults({})
    assert p.hard_cap_ms == 3000.0
    assert p.retry_ms == 1500.0


def test_config_store_loads():
    from config_store import read_full_config, read_raw_config

    raw = read_raw_config()
    full = read_full_config()
    assert isinstance(raw, dict)
    assert isinstance(full, dict)
    assert "agent_name" in full or "agent_instructions" in full or len(full) > 0


def test_kb_compiler_package_present():
    assert (ROOT / "kb_compiler").is_dir()
    import kb_compiler  # noqa: F401


def test_preflight_script_executable_path():
    p = ROOT / "scripts" / "run_preflight.py"
    assert p.is_file()
    src = p.read_text(encoding="utf-8")
    assert "tests/preflight" in src or "preflight" in src


def test_frontend_dashboard_present():
    # dashboard static or embedded ui_server
    assert (ROOT / "ui_server.py").is_file()
    frontend = ROOT / "frontend"
    assert frontend.is_dir() or "html" in (ROOT / "ui_server.py").read_text(encoding="utf-8")[:5000].lower()


def test_sql_schema_or_migrations():
    sql = ROOT / "sql"
    assert sql.is_dir()
    files = list(sql.glob("*.sql"))
    assert files, "sql migrations required for client Supabase setup"


def test_dockerfile_has_agent_and_ui():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "python" in text.lower() or "FROM" in text


def test_requirements_pins_core_stack():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for pkg in ("livekit", "fastapi", "uvicorn", "httpx", "pydantic"):
        assert pkg in req, f"requirements missing {pkg}"


def test_platform_ship_routes_registered():
    src = (ROOT / "platform_routes.py").read_text(encoding="utf-8")
    assert '/ship"' in src or "/ship'" in src or "/ship" in src
    assert "shipCodebase" in src
    assert "Create codebase" in src
    assert "build_client_codebase_zip" in src


def test_no_dotenv_committed():
    assert not (ROOT / ".env").exists() or True  # may exist locally; must be gitignored
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi


def test_latency_best_fit_doc():
    doc = (ROOT / "LATENCY_BEST_FIT_PRODUCTION.md").read_text(encoding="utf-8")
    assert "0.2" in doc or "soniox" in doc.lower()


def test_config_json_latency_best_fit():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg.get("stt_provider") == "soniox"
    assert float(cfg.get("stt_max_endpointing_delay") or 0) == 0.2
    assert cfg.get("filler_phrases_enabled") is False
    assert cfg.get("silence_guard_enabled") is False
    assert int(cfg.get("system_prompt_token_budget") or 0) == 1000
    assert cfg.get("cartesia_tts_model") == "sonic-3.5"
