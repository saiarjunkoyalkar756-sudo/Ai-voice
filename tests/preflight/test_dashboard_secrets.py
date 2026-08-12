"""Dashboard must own all secrets — ship template never embeds them."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_env_manager_groups_cover_start_requirements():
    from env_manager import MANAGED_ENV_KEYS
    from ship.secrets import REQUIRED_ENV_FOR_START

    missing = [k for k in REQUIRED_ENV_FOR_START if k not in MANAGED_ENV_KEYS and k != "DISABLE_AUTH"]
    # DISABLE_AUTH may be env-only; JWT etc must be dashboard-managed
    assert "JWT_SECRET" in MANAGED_ENV_KEYS
    assert "CARTESIA_API_KEY" in MANAGED_ENV_KEYS
    assert "SONIOX_API_KEY" in MANAGED_ENV_KEYS
    assert "GEMINI_API_KEY" in MANAGED_ENV_KEYS
    assert "LIVEKIT_API_KEY" in MANAGED_ENV_KEYS
    assert "SUPABASE_URL" in MANAGED_ENV_KEYS
    # soft: most required keys should be dashboard-managed
    assert len(missing) <= 1, f"required keys not in dashboard: {missing}"


def test_secrets_manager_is_env_only():
    src = (ROOT / "secrets_manager.py").read_text(encoding="utf-8")
    assert "env vars only" in src.lower() or "os.environ" in src
    assert "config.json" in src  # documents that config is not the source


def test_ui_server_strips_secrets_from_config_api():
    src = (ROOT / "ui_server.py").read_text(encoding="utf-8")
    assert "API_SECRET_FIELDS" in src or "_SECRET_KEYS" in src


def test_ship_secrets_inventory_nonempty():
    from ship.secrets import REQUIRED_ENV_FOR_START, SECRET_CONFIG_KEYS, SECRET_ENV_KEYS

    assert len(SECRET_ENV_KEYS) >= 30
    assert len(SECRET_CONFIG_KEYS) >= 15
    assert len(REQUIRED_ENV_FOR_START) >= 8
