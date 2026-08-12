"""End-to-end ship packager tests (uses approved cartridge when available)."""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _approved_client_ids() -> list[str]:
    clients = ROOT / "clients"
    if not clients.is_dir():
        return []
    out = []
    for lock_path in clients.glob("*/compiled.lock.json"):
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (
            lock.get("approved")
            and (lock.get("validation") or {}).get("ok")
            and not (lock.get("critic") or {}).get("blocking")
        ):
            out.append(lock_path.parent.name)
    return out


APPROVED = _approved_client_ids()


@pytest.mark.skipif(not APPROVED, reason="no approved client cartridge on disk")
def test_build_full_codebase_zip_no_secrets():
    from ship.packager import build_client_codebase_zip
    from ship.secrets import scan_text_for_secrets

    client_id = APPROVED[0]
    payload, filename, meta = build_client_codebase_zip(
        ROOT, client_id, shipped_by="preflight-test"
    )
    assert filename.endswith(".zip")
    assert meta["file_count"] > 50
    assert meta["bytes"] == len(payload)
    assert len(payload) > 100_000

    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        assert len(names) == len(set(names)), "zip must not contain duplicate paths"

        # required top-level files
        basenames = {n.split("/", 1)[-1] if "/" in n else n for n in names}
        # paths relative to zip root folder
        rels = []
        for n in names:
            parts = n.split("/", 1)
            rels.append(parts[1] if len(parts) > 1 else parts[0])
        rel_set = set(rels)

        for required in (
            "config.json",
            ".env.example",
            "SHIP_README.md",
            "SHIP_MANIFEST.json",
            "SHIP_COMPLETENESS.json",
            "agent.py",
            "engine/agent_runtime.py",
            "worker_prewarm.py",
            "llm_prewarm.py",
            "greeting_cache.py",
            "scripts/run_preflight.py",
            "scripts/bootstrap_client.py",
            "requirements.txt",
            "cartridge/compiled.lock.json",
            "cartridge/persona.json",
            "data/lang_presets.json",
            "speaker_profiler.py",
            "SPEAKER_PROFILING.md",
            "POST_DOWNLOAD_CHECKLIST.md",
        ):
            assert required in rel_set, f"missing {required} in ship zip"

        # never ship host secrets
        assert not any(r == ".env" or r.endswith("/.env") for r in rels)
        assert not any("node_modules" in r for r in rels)
        assert not any(r.endswith(".pyc") for r in rels)

        cfg_name = next(n for n in names if n.endswith("/config.json") or n.endswith("config.json"))
        cfg = json.loads(zf.read(cfg_name))
        assert cfg.get("ship_meta", {}).get("approved") is True
        assert cfg.get("ship_meta", {}).get("full_production") is True
        assert cfg.get("stt_provider") == "soniox"
        assert cfg.get("filler_phrases_enabled") is False
        assert cfg.get("llm_context_prewarm") is True
        assert cfg.get("speculative_reply_enabled") is True
        assert int(cfg.get("system_prompt_token_budget") or 0) == 1000
        assert cfg.get("agent_instructions"), "approved persona must be baked in"
        assert cfg.get("first_line"), "first dialogue must be baked in"
        assert isinstance(cfg.get("speaker_profiling"), dict), "speaker_profiling block required"
        assert cfg["speaker_profiling"].get("enabled") is False  # opt-in after secrets

        # Completeness report
        comp_name = next(n for n in names if n.endswith("SHIP_COMPLETENESS.json"))
        comp = json.loads(zf.read(comp_name))
        assert comp["checks"]["first_line"] is True
        assert comp["checks"]["worker_prewarm"] is True
        assert comp["checks"]["llm_context_prewarm"] is True
        assert comp["checks"].get("speaker_profiler") is True
        # Prefer ship-time PCM; if platform had no TTS key, bootstrap covers it
        pcm_rels = [r for r in rels if r.startswith("data/greeting_pcm_cache/") and r.endswith(".pcm")]
        if pcm_rels:
            assert comp["checks"]["first_dialogue_pcm"] is True

        for key in (
            "gemini_api_key",
            "cartesia_api_key",
            "soniox_api_key",
            "livekit_api_key",
            "livekit_api_secret",
            "supabase_key",
            "jwt_secret",
        ):
            val = str(cfg.get(key) or "")
            assert not val or "YOUR_" in val, f"ship config leaked {key}"

        env_name = next(n for n in names if n.endswith(".env.example"))
        env_text = zf.read(env_name).decode("utf-8")
        for key in (
            "LIVEKIT_URL",
            "GEMINI_API_KEY",
            "SONIOX_API_KEY",
            "CARTESIA_API_KEY",
            "SUPABASE_URL",
            "JWT_SECRET",
            "SMALLEST_API_KEY",
            "INWORLD_API_KEY",
        ):
            assert key in env_text

        # scan text payloads for secret patterns (allow tests that mention fake keys)
        secret_hits = []
        for n in names:
            if not n.endswith((".py", ".json", ".md", ".yml", ".yaml", ".txt", ".example", ".sql")):
                continue
            if "/tests/" in n:
                continue  # unit tests may contain fake key strings
            try:
                text = zf.read(n).decode("utf-8", "replace")
            except Exception:
                continue
            hits = scan_text_for_secrets(text)
            if hits:
                secret_hits.append((n, hits))
        assert not secret_hits, f"secret patterns in ship: {secret_hits[:5]}"


@pytest.mark.skipif(not APPROVED, reason="no approved client cartridge on disk")
def test_shipped_dashboard_is_client_branded():
    """The generated codebase's dashboard must carry the approved client's brand,
    not the VK Realty demo brand — while keeping asset paths/slug functional."""
    import yaml

    from ship.packager import build_client_codebase_zip

    client_id = APPROVED[0]
    manifest = yaml.safe_load((ROOT / "clients" / client_id / "client.yaml").read_text("utf-8")) or {}
    brand = str((manifest.get("persona") or {}).get("company") or "").strip()
    if not brand or brand.lower() == "vk realty":
        pytest.skip("approved client has no distinct brand to assert")

    payload, _filename, _meta = build_client_codebase_zip(
        ROOT, client_id, shipped_by="preflight-test", skip_prebake=True
    )
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        html_pages = [n for n in names if n.endswith("frontend/tinglish-vk-realty/dashboard.html")]
        assert html_pages, "shipped dashboard.html not found"
        dash = zf.read(html_pages[0]).decode("utf-8")

        assert brand in dash, "client brand missing from shipped dashboard"
        assert "VK Realty" not in dash, "VK Realty demo brand leaked into shipped dashboard HTML"
        # Runtime JS must not re-stamp the old brand as the document title
        js_pages = [n for n in names if n.endswith("frontend/tinglish-vk-realty/vk-realty-dashboard.js")]
        if js_pages:
            js = zf.read(js_pages[0]).decode("utf-8")
            assert "VK Realty" not in js, "VK Realty leaked into shipped dashboard JS"
        # Functional asset paths / slug stay intact so the dashboard still loads
        assert "/static/tinglish-vk-realty/" in dash
        assert "vk-realty-dashboard.css" in dash


def test_ship_rejects_unapproved():
    from ship.packager import ShipError, build_client_codebase_zip

    with pytest.raises(ShipError):
        build_client_codebase_zip(ROOT, "__no_such_client__")


def test_ship_rejects_unapproved_real_client():
    """If an unapproved cartridge exists, ship must 409-style refuse."""
    from ship.packager import ShipError, build_client_codebase_zip

    clients = ROOT / "clients"
    if not clients.is_dir():
        pytest.skip("no clients dir")
    for lock_path in clients.glob("*/compiled.lock.json"):
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if not lock.get("approved"):
            with pytest.raises(ShipError, match="[Nn]ot approved|Not compiled|Validation|Critic"):
                build_client_codebase_zip(ROOT, lock_path.parent.name)
            return
    pytest.skip("no unapproved client to test")
