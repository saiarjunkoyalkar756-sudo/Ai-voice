"""Template hygiene — what we ship must be production-safe structure."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_root_py_modules_syntax():
    """Compile critical root modules (syntax only — fast)."""
    import py_compile

    critical = [
        "agent.py",
        "ui_server.py",
        "platform_routes.py",
        "dashboard_routes.py",
        "env_manager.py",
        "secrets_manager.py",
        "config_store.py",
        "ship/packager.py",
        "ship/secrets.py",
        "engine/agent_runtime.py",
        "engine/conversation_engine.py",
        "scripts/run_preflight.py",
    ]
    for rel in critical:
        path = ROOT / rel
        assert path.is_file(), rel
        py_compile.compile(str(path), doraise=True)


def test_packager_include_list_covers_engine():
    from ship.packager import _ROOT_EXTRA, _WALK_ROOTS, _iter_template_files

    assert "engine" in _WALK_ROOTS
    assert "scripts" in _WALK_ROOTS
    assert "requirements.txt" in _ROOT_EXTRA
    files = _iter_template_files(ROOT)
    names = {p.name for p in files}
    assert "agent.py" in names
    assert "ui_server.py" in names
    assert "worker_prewarm.py" in names
    assert "llm_prewarm.py" in names
    assert "greeting_cache.py" in names


def test_exclude_list_blocks_secrets_and_bloat():
    from ship.packager import _EXCLUDE_DIR_NAMES, _EXCLUDE_FILE_NAMES

    assert ".env" in _EXCLUDE_FILE_NAMES
    assert "config.json" in _EXCLUDE_FILE_NAMES  # rebuilt sanitized
    assert "node_modules" in _EXCLUDE_DIR_NAMES
    assert "clients" in _EXCLUDE_DIR_NAMES
    assert ".git" in _EXCLUDE_DIR_NAMES


def test_ship_env_example_generator():
    from ship.packager import _env_example

    text = _env_example()
    assert "LIVEKIT_URL=" in text
    assert "GEMINI_API_KEY=" in text
    assert "SONIOX_API_KEY=" in text
    assert "CARTESIA_API_KEY=" in text
    assert "SUPABASE_URL=" in text
    assert "JWT_SECRET=" in text
    assert "STT_PROVIDER=soniox" in text
    assert "TTS_PROVIDER=cartesia" in text
    # must not contain real-looking secrets
    assert "sk_car_" not in text
    assert "AIza" not in text


def test_sanitize_strips_nested_style_keys():
    from ship.secrets import sanitize_config

    dirty = {
        "openai_api_key": "sk-abcdefghijklmnopqrstuvwxyz12",
        "dashboard_password": "SuperSecretPass123!",
        "agent_name": "Arjun",
        "crm_webhook_secret": "whsec_abc123xyz",
    }
    clean = sanitize_config(dirty)
    assert clean["openai_api_key"] == ""
    assert clean["dashboard_password"] == ""
    assert clean["agent_name"] == "Arjun"
    assert clean.get("crm_webhook_secret") in ("", None)


def test_looks_like_secret_false_positives():
    from ship.secrets import looks_like_secret_value

    assert not looks_like_secret_value("")
    assert not looks_like_secret_value("wss://YOUR_PROJECT.livekit.cloud")
    assert not looks_like_secret_value("admin")
    assert looks_like_secret_value("sk_car_qWGcJ7mVFmpjffqDsriNi1")
    assert looks_like_secret_value("AIzaSyRealKey1234567890abcd")
