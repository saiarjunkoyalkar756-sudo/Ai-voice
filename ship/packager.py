"""
Pack a production client codebase = full template + approved cartridge + prewarm.

Output: speaksy-client-{client_id}-{utc}.zip
  - Complete engine, dashboard, SQL, scripts, tests
  - Approved persona / packs / first dialogue
  - Latency best-fit + full production knobs
  - Ship-time prebake of first dialogue + greeting PCM (when platform has TTS key)
  - No API keys / no host .env
  - Client fills secrets via .env or dashboard Settings
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ship.secrets import SECRET_ENV_KEYS, sanitize_config

logger = logging.getLogger("speaksy-ship")

COMPILER_VERSION = "1.0.0"


class ShipError(RuntimeError):
    pass


# ── Dashboard rebranding ─────────────────────────────────────────────────────
# The template dashboard carries the VK Realty demo brand. When we ship a client
# codebase we rewrite the *visible* brand to the approved client's company name
# so the operator gets a complete, on-brand dashboard out of the box.

_WORDMARK_DASHBOARD_RE = re.compile(
    r'<span class="brand-wordmark-line brand-wordmark-vk">VK</span>\s*'
    r'<span class="brand-wordmark-line brand-wordmark-realty">\s*Realty</span>'
)
_WORDMARK_INLINE_RE = re.compile(
    r'<span class="wm-vk">VK</span><span class="wm-realty">\s*Realty</span>'
)


def _rebrand_frontend_asset(text: str, brand: str, agent: str = "") -> str:
    """Rewrite the visible VK Realty brand in a shipped dashboard page or script
    to the approved client's company name.

    Touches human-visible text, aria-labels and runtime display strings ONLY
    (e.g. ``document.title = "VK Realty — Dashboard"`` in the dashboard JS, which
    would otherwise re-stamp the old brand after load). It never rewrites class
    names (``vk-realty-*``, ``wm-vk``), asset paths
    (``/static/tinglish-vk-realty/…``) or the URL slug — those use a different
    casing/hyphenation than the spaced, capitalised ``VK Realty`` token and stay
    functional so the shipped dashboard loads unchanged, just on-brand.
    """
    if not brand:
        return text
    # Two-span wordmarks → one branded span (keep a wordmark class so the
    # existing display styling still applies to arbitrary-length names).
    text = _WORDMARK_DASHBOARD_RE.sub(
        f'<span class="brand-wordmark-line brand-wordmark-vk">{brand}</span>', text
    )
    text = _WORDMARK_INLINE_RE.sub(f'<span class="wm-vk">{brand}</span>', text)
    # Plain visible brand text + aria-labels + input defaults.
    text = text.replace("VK Realty", brand)
    # Agent display name in card titles / placeholder copy.
    if agent:
        display = agent if agent[:1].isupper() else agent[:1].upper() + agent[1:]
        text = re.sub(r"\bArjun\b", display, text)
    return text


# ── Exclusions ──────────────────────────────────────────────────────────────

_EXCLUDE_DIR_NAMES = frozenset({
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    "docs-docus",
    "docs-nextra",
    "whatsapp-service",
    "flow-builder",  # optional React; not required for voice agent
    "clients",       # other cartridges never ship
    "logs",
    "backups",
    "live_test",
    "agent_logs",
    "shipments",
})

_EXCLUDE_FILE_NAMES = frozenset({
    ".env",
    ".DS_Store",
    "config.json",  # rebuilt sanitized + approved
    "tenancy.db",
    "config_reload.signal",
})

_EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".log", ".db")

# data/*.json always included (templates + engine tables)
_DATA_JSON_ALLOW = frozenset({
    "preset_schema.json",
    "preset_reply_variants.json",
    "lang_presets.json",
    "employee_backstory.json",
    "registry.json",
    "company_knowledge.json",
})

_WALK_ROOTS = (
    "engine",
    "kb_compiler",
    "re_voice_memory",
    "knowledge_system",
    "knowledge_data",
    "sql",
    "scripts",
    "tests",
    "frontend",
    "ship",
    "docs_html",
    "data",
)

# Always try these root docs / deploy assets
_ROOT_EXTRA = (
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
    "supervisord.conf",
    "CICD-1.ogg",
    ".gitignore",
    "README.md",
    "LATENCY_BEST_FIT_PRODUCTION.md",
    "CLIENT_SHIP.md",
    "CLIENT_SETUP.md",
    "POST_DOWNLOAD_CHECKLIST.md",
    "SPEAKER_PROFILING.md",
    "FULL_CONTEXT.md",
)


def _should_skip(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    if set(rel.parts) & _EXCLUDE_DIR_NAMES:
        return True
    if path.name in _EXCLUDE_FILE_NAMES:
        return True
    if path.name.startswith(".env") and path.name != ".env.example":
        return True
    if path.suffix in _EXCLUDE_SUFFIXES:
        return True
    if "node_modules" in rel.parts:
        return True
    # Host greeting cache PCMs are mixed/stale — ship only ship-time prebake
    if "greeting_pcm_cache" in rel.parts and path.suffix == ".pcm":
        return True
    if path.suffix == ".pcm":
        return True
    return False


def _iter_template_files(root: Path) -> list[Path]:
    """Include the full production tree (all root modules + packages)."""
    files: list[Path] = []

    # All root-level Python modules (complete coverage — no allowlist gaps)
    for p in root.glob("*.py"):
        if p.is_file() and not _should_skip(p, root):
            files.append(p)

    for name in _ROOT_EXTRA:
        p = root / name
        if p.is_file() and not _should_skip(p, root):
            files.append(p)

    for sub in _WALK_ROOTS:
        base = root / sub
        if not base.exists():
            continue
        if base.is_file():
            if not _should_skip(base, root):
                files.append(base)
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if _should_skip(path, root):
                continue
            # data filters
            if "data" in path.parts:
                rel_parts = path.relative_to(root).parts
                if "greeting_pcm_cache" in rel_parts:
                    continue
                if "company_knowledge" in rel_parts and path.suffix == ".json":
                    # host packs replaced by approved cartridge packs
                    continue
                if path.suffix == ".json" and path.name not in _DATA_JSON_ALLOW:
                    # inventory / market for other presets may still be useful as empty fallbacks
                    if not (
                        path.name.endswith("_inventory.json")
                        or path.name.endswith("_market_competitor.json")
                    ):
                        # skip host-specific noise (conversion_events, etc.)
                        if path.name not in (
                            "lang_presets.json",
                            "preset_schema.json",
                            "preset_reply_variants.json",
                            "employee_backstory.json",
                        ):
                            continue
            try:
                if path.stat().st_size > 12 * 1024 * 1024:
                    continue
            except OSError:
                continue
            files.append(path)

    seen: set[Path] = set()
    out: list[Path] = []
    for f in sorted(files):
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


# ── Full production config ───────────────────────────────────────────────────

_PRODUCTION_LATENCY: dict[str, Any] = {
    # STT — Soniox best-fit
    "stt_provider": "soniox",
    "stt_min_endpointing_delay": 0.2,
    "stt_max_endpointing_delay": 0.2,
    "stt_max_endpoint_delay_ms": 200,
    "stt_silence_timeout_ms": 200,
    "stt_enable_endpoint_detection": True,
    "stt_adaptive_endpoint_enabled": True,
    "stt_enable_language_identification": True,
    # TTS — Cartesia sonic-3.5
    "tts_provider": "cartesia",
    "cartesia_tts_model": "sonic-3.5",
    "first_tts_chunk_fast_path": True,
    "tts_aggressive_chunking_enabled": True,
    # LLM
    "llm_streaming": True,
    "llm_context_prewarm": True,
    "llm_startup_probe": False,
    "llm_tiered_retry_ms": 1500,
    "llm_tiered_hard_cap_ms": 3000,
    "llm_circuit_sla_ms": 3000,
    "system_prompt_token_budget": 1000,
    # Turn path
    "parallel_turn_injectors_enabled": True,
    "speculative_reply_enabled": True,
    "speculative_partial_enabled": True,
    "speculative_partial_match_threshold": 0.9,
    "speculative_partial_stable_ms": 250,
    "speculative_reply_min_speech_ms": 2000,
    "stable_prefix_cache_enabled": True,
    # Production: filler/silence off (best-fit path)
    "filler_phrases_enabled": False,
    "silence_guard_enabled": False,
}

# Speaker age/gender sidecar (Inworld + Smallest) — always present in ships
_SPEAKER_PROFILING_DEFAULT: dict[str, Any] = {
    "enabled": False,  # client enables after setting SMALLEST_API_KEY + INWORLD_API_KEY
    "window_s": 6.0,
    "deadline_s": 7.0,
    "age_conf_min": 0.6,
    "gender_provider_prior": 0.8,
    "silence_rms_floor": 350,
    "inworld_model_id": "inworld/inworld-stt-1",
    "inworld_top_n": 3,
    "smallest_model": "pulse",
    "language": "en",
    "inject_into_llm": True,
    "store_in_analytics": True,
    "emotion_detection": True,
}


def _build_ship_config(
    repo_root: Path,
    cdir: Path,
    lock: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Sanitized config.json with full production knobs + approved agent fields."""
    base_path = repo_root / "config.json"
    raw: dict[str, Any] = {}
    if base_path.is_file():
        raw = json.loads(base_path.read_text(encoding="utf-8"))
    cfg = sanitize_config(raw)

    # Full production latency / path knobs (override host experiments)
    cfg.update(_PRODUCTION_LATENCY)

    # Always ship speaker-profiling block (code is in template; keys via .env)
    sp = cfg.get("speaker_profiling")
    if not isinstance(sp, dict):
        sp = {}
    merged_sp = {**_SPEAKER_PROFILING_DEFAULT, **sp}
    # Never ship enabled=true with missing client keys — default off for safety
    merged_sp["enabled"] = bool(merged_sp.get("enabled")) and False  # force off in ship
    # Actually: always ship disabled so client opts in after secrets
    merged_sp["enabled"] = False
    cfg["speaker_profiling"] = merged_sp

    # Approved persona / packs identity
    persona: dict = {}
    pp = cdir / "persona.json"
    if pp.is_file():
        persona = json.loads(pp.read_text(encoding="utf-8"))
    if persona.get("agent_instructions"):
        cfg["agent_instructions"] = persona["agent_instructions"]
    if persona.get("first_line"):
        cfg["first_line"] = persona["first_line"]
    if persona.get("stt_hints"):
        cfg["stt_hints"] = persona["stt_hints"]

    if manifest.get("lang_preset"):
        cfg["lang_preset"] = manifest["lang_preset"]
    if manifest.get("industry"):
        cfg["agent_purpose"] = manifest.get("industry")

    llm = manifest.get("llm") or {}
    if llm.get("model"):
        cfg["llm_model"] = llm["model"]
        cfg["gemini_model"] = llm["model"]
    if llm.get("temperature") is not None:
        cfg["llm_temperature"] = llm["temperature"]
    if llm.get("max_tokens"):
        cfg["llm_max_completion_tokens"] = llm["max_tokens"]

    voice = manifest.get("voice") or {}
    if voice.get("voice_id"):
        cfg["tts_voice"] = voice["voice_id"]
    if voice.get("tts_provider"):
        cfg["tts_provider"] = voice["tts_provider"]
    if voice.get("tts_model"):
        if str(cfg.get("tts_provider")) == "cartesia":
            cfg["cartesia_tts_model"] = voice["tts_model"]
        else:
            cfg["gemini_tts_model"] = voice["tts_model"]
    if voice.get("language"):
        cfg["tts_language"] = voice["language"]

    persona_m = manifest.get("persona") or {}
    if persona_m.get("name") or persona_m.get("company"):
        cfg["agent_name"] = str(
            persona_m.get("name") or cfg.get("agent_name") or "Agent"
        )
        if persona_m.get("company"):
            cfg["company_name"] = persona_m["company"]

    # Ensure idle/ending lines exist for session prewarm (fallbacks)
    if not isinstance(cfg.get("user_idle"), dict):
        cfg["user_idle"] = {}
    ui = cfg["user_idle"]
    if not ui.get("prompt_message"):
        ui["prompt_message"] = "Hello? Are you still there?"
    if not ui.get("last_message"):
        ui["last_message"] = "I'll disconnect now. Feel free to call back anytime. Bye!"
    if not isinstance(cfg.get("call_ending"), dict):
        cfg["call_ending"] = {}
    if not cfg["call_ending"].get("message"):
        cfg["call_ending"]["message"] = "Thank you for your time. Have a great day. Bye!"

    cfg["client_id"] = cdir.name
    cfg["ship_meta"] = {
        "client_id": cdir.name,
        "shipped_at": datetime.now(timezone.utc).isoformat(),
        "compiler_version": lock.get("compiler_version"),
        "pack_id": lock.get("pack_id"),
        "approved": True,
        "secrets_via": "env_or_dashboard",
        "full_production": True,
        "includes_prewarm": True,
        "bootstrap": "python3 scripts/bootstrap_client.py",
    }
    return cfg


def _ship_readme(client_id: str, manifest: dict[str, Any], prebake: dict[str, Any]) -> str:
    company = (manifest.get("persona") or {}).get("company") or client_id
    pcm_n = prebake.get("pcm_count") or len(prebake.get("pcm_files") or [])
    prebake_line = (
        f"- **First dialogue pre-baked** ({pcm_n} PCM files in `data/greeting_pcm_cache/`)"
        if pcm_n
        else "- First dialogue texts baked into config; run `bootstrap_client.py` to synthesize PCM with your TTS key"
    )
    return f"""# Speaksy Client Codebase — `{client_id}`

Production agent package for **{company}**.

## What is already baked in (full production)

- Complete voice engine (LiveKit agent + dashboard UI + SQL + scripts)
- Approved persona, first line, STT hints, knowledge packs
- Latency best-fit (Soniox 0.2/0.2, Cartesia sonic-3.5, Gemini streaming, TTFT 1.5s/3s)
- LLM context prewarm + speculative reply path + parallel injectors
- Worker prewarm path (greetings, knowledge packs, IQ registry)
- **Speaker age/gender profiler** (`speaker_profiler.py`) — Inworld age + Smallest gender sidecar (off by default; set keys + enable)
{prebake_line}
- Preflight + bootstrap scripts — **run before every production start**
- `POST_DOWNLOAD_CHECKLIST.md` + `SPEAKER_PROFILING.md`

## What you must configure (secrets only)

1. Copy `.env.example` → `.env` and fill keys, **or**
2. Dashboard **Settings → API keys** after first login

| Group | Keys |
|-------|------|
| LiveKit | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| LLM | `GEMINI_API_KEY` |
| STT | `SONIOX_API_KEY` |
| TTS | `CARTESIA_API_KEY` |
| Database | `SUPABASE_URL`, `SUPABASE_KEY` (+ service role recommended) |
| Auth | `JWT_SECRET`, `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD` |
| Optional | Telephony / SIP, S3 recordings, Cal.com, Sentry |
| Speaker profile (optional) | `SMALLEST_API_KEY`, `INWORLD_API_KEY` then set `speaker_profiling.enabled=true` |

**No secrets are included in this zip.**

## Bootstrap (mandatory first run)

```bash
cp .env.example .env   # fill secrets
python3 scripts/bootstrap_client.py
# = prewarm first dialogue + greetings + knowledge packs + preflight
```

Or step by step:

```bash
python3 scripts/bootstrap_client.py --prewarm-only
python3 scripts/run_preflight.py
```

Exit **0** required before:

```bash
python3 agent.py start
uvicorn ui_server:app --host 0.0.0.0 --port 8000
```

## Deploy sketch

```bash
cp .env.example .env
python3 scripts/bootstrap_client.py
docker compose up -d   # or supervisord
```

## Support

Generated by Speaksy Platform → **Create codebase** (after Approve).
"""


def _env_example() -> str:
    lines = [
        "# Speaksy client — fill all values. Never commit this file.",
        "# Dashboard can also store secrets after first login.",
        "",
    ]
    for k in SECRET_ENV_KEYS:
        if k in ("DISABLE_AUTH",):
            lines.append(f"{k}=false")
        elif k == "ENVIRONMENT":
            lines.append(f"{k}=production")
        elif k == "STT_PROVIDER":
            lines.append("STT_PROVIDER=soniox")
        elif k == "TTS_PROVIDER":
            lines.append("TTS_PROVIDER=cartesia")
        elif k == "CARTESIA_TTS_MODEL":
            lines.append("CARTESIA_TTS_MODEL=sonic-3.5")
        elif k == "SUPABASE_S3_REGION":
            lines.append(f"{k}=ap-south-1")
        elif k == "SUPABASE_RECORDINGS_BUCKET":
            lines.append(f"{k}=call-recordings")
        else:
            lines.append(f"{k}=")
    lines.append("")
    return "\n".join(lines)


def _completeness_checklist(
    file_map: dict[str, bytes],
    ship_config: dict[str, Any],
    prebake: dict[str, Any],
) -> dict[str, Any]:
    rels = set(file_map)
    checks = {
        "agent_shim": "agent.py" in rels,
        "agent_runtime": "engine/agent_runtime.py" in rels,
        "worker_prewarm": "worker_prewarm.py" in rels,
        "llm_prewarm": "llm_prewarm.py" in rels,
        "greeting_cache": "greeting_cache.py" in rels,
        "ui_server": "ui_server.py" in rels,
        "bootstrap": "scripts/bootstrap_client.py" in rels,
        "preflight": "scripts/run_preflight.py" in rels,
        "sql": any(r.startswith("sql/") and r.endswith(".sql") for r in rels),
        "requirements": "requirements.txt" in rels,
        "config": "config.json" in rels,
        "env_example": ".env.example" in rels,
        "first_line": bool(str(ship_config.get("first_line") or "").strip()),
        "agent_instructions": bool(str(ship_config.get("agent_instructions") or "").strip()),
        "stt_hints": bool(ship_config.get("stt_hints")),
        "llm_context_prewarm": ship_config.get("llm_context_prewarm") is True,
        "latency_best_fit": (
            ship_config.get("stt_provider") == "soniox"
            and float(ship_config.get("stt_max_endpointing_delay") or 0) == 0.2
            and ship_config.get("filler_phrases_enabled") is False
            and int(ship_config.get("system_prompt_token_budget") or 0) == 1000
        ),
        "knowledge_pack": any(
            r.startswith("data/company_knowledge/") and r.endswith(".json") for r in rels
        ),
        "cartridge_lock": "cartridge/compiled.lock.json" in rels,
        "cartridge_persona": "cartridge/persona.json" in rels,
        "first_dialogue_pcm": any(
            r.startswith("data/greeting_pcm_cache/") and r.endswith(".pcm") for r in rels
        ),
        "lang_presets": "data/lang_presets.json" in rels,
        "frontend_or_ui": "ui_server.py" in rels,
        "speaker_profiler": "speaker_profiler.py" in rels,
        "speaker_profiling_config": isinstance(
            ship_config.get("speaker_profiling"), dict
        ),
        "speaker_docs": "SPEAKER_PROFILING.md" in rels,
        "post_download_checklist": "POST_DOWNLOAD_CHECKLIST.md" in rels,
    }
    missing = [k for k, ok in checks.items() if not ok]
    return {
        "checks": checks,
        "missing": missing,
        "all_ok": not missing or missing == ["first_dialogue_pcm"],  # pcm optional if no platform key
        "prebake": {
            "ok": prebake.get("ok"),
            "pcm_count": prebake.get("pcm_count") or len(prebake.get("pcm_files") or []),
            "error": prebake.get("error"),
            "provider": prebake.get("provider"),
            "first_line": prebake.get("first_line"),
        },
    }


def build_client_codebase_zip(
    repo_root: Path,
    client_id: str,
    *,
    shipped_by: str = "",
    skip_prebake: bool = False,
) -> tuple[bytes, str, dict[str, Any]]:
    """Build full production shippable zip. Requires approved cartridge."""
    from kb_compiler.bake import client_dir, load_lock

    root = repo_root.resolve()
    cdir = client_dir(root, client_id)
    if not (cdir / "client.yaml").is_file():
        raise ShipError(f"Client {client_id} not found")

    lock = load_lock(cdir)
    if not lock:
        raise ShipError("Not compiled — run compile first")
    if not lock.get("approved"):
        raise ShipError("Not approved — Approve & make LIVE first")
    if not (lock.get("validation") or {}).get("ok"):
        raise ShipError("Validation not OK — fix and recompile")
    if lock.get("critic", {}).get("blocking"):
        raise ShipError("Critic blockers remain — fix and recompile")

    import yaml

    manifest = yaml.safe_load((cdir / "client.yaml").read_text(encoding="utf-8")) or {}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root_name = f"speaksy-client-{client_id}-{stamp}"
    filename = f"{root_name}.zip"

    ship_config = _build_ship_config(root, cdir, lock, manifest)
    # safety: reject if any secret-looking value slipped in
    for k, v in ship_config.items():
        if k in ("agent_instructions", "first_line", "ship_meta", "stt_hints", "company_name"):
            continue
        if isinstance(v, str) and k.lower().endswith(("key", "secret", "password")):
            if v and "YOUR_" not in v and len(v) > 8:
                ship_config[k] = ""

    if not str(ship_config.get("first_line") or "").strip():
        raise ShipError("Approved persona has empty first_line — cannot ship without first dialogue")
    if not str(ship_config.get("agent_instructions") or "").strip():
        raise ShipError("Approved persona has empty agent_instructions")

    # ── Ship-time prebake (first dialogue + greetings) ─────────────────────
    prebake_report: dict[str, Any] = {"ok": False, "skipped": skip_prebake}
    prebake_files: dict[str, bytes] = {}
    if not skip_prebake:
        try:
            from ship.prebake import prebake_for_ship

            prebake_files, prebake_report = prebake_for_ship(ship_config)
            logger.info(
                "[SHIP] Prebake pcm=%s ok=%s err=%s",
                prebake_report.get("pcm_count") or len(prebake_report.get("pcm_files") or []),
                prebake_report.get("ok"),
                prebake_report.get("error"),
            )
        except Exception as exc:
            logger.exception("[SHIP] Prebake failed (continuing without PCM)")
            prebake_report = {"ok": False, "error": str(exc)}

    # rel → bytes (later writes win)
    file_map: dict[str, bytes] = {}

    def add_bytes(rel: str, data: bytes) -> None:
        file_map[rel.replace("\\", "/")] = data

    def add_text(rel: str, text: str) -> None:
        add_bytes(rel, text.encode("utf-8"))

    # Full template source tree — client-brand the shipped dashboard pages
    brand = str(ship_config.get("company_name") or "").strip()
    agent_name = str((manifest.get("persona") or {}).get("name") or "").strip()
    for path in _iter_template_files(root):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("ship/shipments/"):
            continue
        if rel in (".env.example", "config.json"):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if brand and rel.startswith("frontend/") and rel.endswith((".html", ".js")):
            try:
                data = _rebrand_frontend_asset(
                    data.decode("utf-8"), brand, agent_name
                ).encode("utf-8")
            except (UnicodeDecodeError, ValueError):
                pass
        add_bytes(rel, data)

    # Approved packs
    packs = cdir / "packs"
    pack_id = str(lock.get("pack_id") or manifest.get("lang_preset") or "tinglish")
    if packs.is_dir():
        mapping = {
            "company_knowledge.json": f"data/company_knowledge/{pack_id}.json",
            "inventory.json": f"data/{pack_id}_inventory.json",
            "market_competitor.json": f"data/{pack_id}_market_competitor.json",
        }
        for src_name, dest in mapping.items():
            src = packs / src_name
            if src.is_file():
                add_bytes(dest, src.read_bytes())

    # Also map pack into knowledge_data if used by runtime
    ck = packs / "company_knowledge.json" if packs.is_dir() else None
    if ck and ck.is_file():
        add_bytes("knowledge_data/company_knowledge.json", ck.read_bytes())

    # Cartridge audit copy
    for name in (
        "client.yaml",
        "persona.json",
        "compiled.lock.json",
        "artifacts.json",
        "facts.json",
    ):
        p = cdir / name
        if p.is_file():
            add_bytes(f"cartridge/{name}", p.read_bytes())

    # Prebaked first dialogue / greetings
    for rel, data in prebake_files.items():
        add_bytes(rel, data)

    # Sanitized config + env + docs
    ship_config["ship_meta"]["prebake"] = {
        "ok": prebake_report.get("ok"),
        "pcm_count": prebake_report.get("pcm_count")
        or len(prebake_report.get("pcm_files") or []),
        "provider": prebake_report.get("provider"),
        "error": prebake_report.get("error"),
    }
    add_text("config.json", json.dumps(ship_config, indent=2, ensure_ascii=False) + "\n")
    add_text(".env.example", _env_example())
    add_text("SHIP_README.md", _ship_readme(client_id, manifest, prebake_report))

    # Empty runtime dirs
    for keep in (
        "data/company_knowledge/.gitkeep",
        "data/agent_logs/.gitkeep",
        "data/greeting_pcm_cache/.gitkeep",
        "data/campaigns/.gitkeep",
        "data/latency_baselines/.gitkeep",
    ):
        if keep not in file_map:
            add_text(keep, "")

    checklist = _completeness_checklist(file_map, ship_config, prebake_report)
    add_text(
        "SHIP_COMPLETENESS.json",
        json.dumps(checklist, indent=2, ensure_ascii=False) + "\n",
    )

    inventory = [
        {
            "path": rel,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()[:16],
        }
        for rel, data in sorted(file_map.items())
    ]
    manifest_body = {
        "format": "speaksy.client.codebase",
        "format_version": "1.1",
        "client_id": client_id,
        "shipped_at": datetime.now(timezone.utc).isoformat(),
        "shipped_by": shipped_by or None,
        "approved": True,
        "full_production": True,
        "pack_id": pack_id,
        "lang_preset": manifest.get("lang_preset"),
        "industry": manifest.get("industry"),
        "persona": manifest.get("persona"),
        "first_line": str(ship_config.get("first_line") or "")[:200],
        "prebake": ship_config["ship_meta"].get("prebake"),
        "completeness": checklist,
        "file_count": 0,
        "required_secrets": list(SECRET_ENV_KEYS),
        "bootstrap": "python3 scripts/bootstrap_client.py",
        "preflight": "python3 scripts/run_preflight.py",
        "files": inventory,
    }
    add_text("SHIP_MANIFEST.json", json.dumps(manifest_body, indent=2, ensure_ascii=False) + "\n")
    # refresh inventory with manifest
    inventory = [
        {
            "path": rel,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()[:16],
        }
        for rel, data in sorted(file_map.items())
    ]
    manifest_body["file_count"] = len(file_map)
    manifest_body["files"] = inventory
    add_text("SHIP_MANIFEST.json", json.dumps(manifest_body, indent=2, ensure_ascii=False) + "\n")

    payloads = sorted(file_map.items())

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel, data in payloads:
            info = zipfile.ZipInfo(filename=f"{root_name}/{rel}")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.date_time = datetime.now(timezone.utc).timetuple()[:6]
            zf.writestr(info, data)

    payload = buf.getvalue()
    meta = {
        "client_id": client_id,
        "filename": filename,
        "bytes": len(payload),
        "file_count": len(payloads),
        "shipped_by": shipped_by,
        "pack_id": pack_id,
        "prebake_pcm": ship_config["ship_meta"]["prebake"].get("pcm_count"),
        "prebake_ok": ship_config["ship_meta"]["prebake"].get("ok"),
        "completeness_ok": checklist.get("all_ok"),
        "missing": checklist.get("missing"),
    }
    logger.info(
        "[SHIP] %s → %s (%d files, %d bytes, pcm=%s)",
        client_id,
        filename,
        len(payloads),
        len(payload),
        meta.get("prebake_pcm"),
    )
    return payload, filename, meta
