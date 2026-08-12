"""Unit tests for ship packager (no full zip unless cartridge approved)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_build_ship_config_sanitizes(tmp_path, monkeypatch):
    from ship.packager import _build_ship_config

    # minimal fake cartridge
    cdir = tmp_path / "client_x"
    cdir.mkdir()
    (cdir / "client.yaml").write_text(
        "client_id: client_x\nlang_preset: tinglish\n"
        "persona:\n  name: Arjun\n  company: DemoCo\n"
        "voice:\n  tts_provider: cartesia\n"
        "llm:\n  model: gemini-2.5-flash\n  temperature: 0.55\n  max_tokens: 200\n",
        encoding="utf-8",
    )
    (cdir / "persona.json").write_text(
        json.dumps({
            "agent_instructions": "You are Arjun at DemoCo.",
            "first_line": "Hello andi!",
            "stt_hints": ["DemoCo"],
        }),
        encoding="utf-8",
    )
    # use real repo as root for base config
    lock = {"compiler_version": "1.0.0", "pack_id": "tinglish", "approved": True}
    import yaml

    manifest = yaml.safe_load((cdir / "client.yaml").read_text())
    cfg = _build_ship_config(ROOT, cdir, lock, manifest)
    assert cfg["agent_instructions"] == "You are Arjun at DemoCo."
    assert cfg["first_line"] == "Hello andi!"
    assert cfg["lang_preset"] == "tinglish"
    assert cfg.get("gemini_api_key") in ("", None) or "YOUR" in str(cfg.get("gemini_api_key"))
    assert cfg["stt_provider"] == "soniox"
    assert cfg["filler_phrases_enabled"] is False
    assert cfg["system_prompt_token_budget"] == 1000
    assert cfg["ship_meta"]["client_id"] == "client_x"


def test_ship_error_if_not_approved():
    from ship.packager import ShipError, build_client_codebase_zip

    with pytest.raises(ShipError):
        # use a fake id that won't be approved
        build_client_codebase_zip(ROOT, "no-such-client-xyz")
