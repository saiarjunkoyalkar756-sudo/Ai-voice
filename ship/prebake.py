"""
Ship-time prewarm of first dialogue + greeting/session/reply PCM.

Strategy:
  1. Load platform .env for TTS keys (never written into the ZIP)
  2. Seed ship cache from host data/greeting_pcm_cache (matching voice/model/text keys)
  3. Synthesize any misses via Cartesia/Gemini/Sarvam
  4. Always prioritize first_line — must be in ZIP when any audio source works

PCM files land under data/greeting_pcm_cache/ so the client agent starts hot.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("speaksy-ship.prebake")


def _ensure_dotenv() -> None:
    """Load platform host .env so ship-time TTS prebake can use keys (never written to ZIP)."""
    try:
        from dotenv import load_dotenv

        root = Path(__file__).resolve().parents[1]
        load_dotenv(root / ".env")
    except Exception:
        pass


def _resolve_api_key(tts_provider: str) -> str:
    _ensure_dotenv()
    if tts_provider == "cartesia":
        return (os.environ.get("CARTESIA_API_KEY") or "").strip()
    if tts_provider == "sarvam":
        return (os.environ.get("SARVAM_API_KEY") or "").strip()
    return (
        (os.environ.get("GEMINI_API_KEY") or "").strip()
        or (os.environ.get("GOOGLE_API_KEY") or "").strip()
    )


def _seed_from_host_cache(
    *,
    host_cache: Path,
    ship_cache: Path,
    items: list[tuple[str, str, str]],
    tts_provider: str,
    tts_voice: str,
    tts_model: str,
    voice_per_lang: dict[str, str],
) -> int:
    """Copy matching PCM keys from host cache into ship staging. Returns count copied."""
    from greeting_cache import _disk_cache_key

    if not host_cache.is_dir():
        return 0
    ship_cache.mkdir(parents=True, exist_ok=True)
    copied = 0
    for lang, text, _kind in items:
        voice = voice_per_lang.get(lang) or tts_voice
        if not voice or not text:
            continue
        key = _disk_cache_key(
            provider=tts_provider,
            voice=voice,
            model=tts_model if tts_provider == "cartesia" else (
                tts_model if tts_provider == "gemini" else ""
            ),
            text=text,
        )
        src = host_cache / f"{key}.pcm"
        if src.is_file() and src.stat().st_size > 0:
            dst = ship_cache / f"{key}.pcm"
            if not dst.exists():
                shutil.copy2(src, dst)
                copied += 1
    return copied


async def _prebake_first_line_only(
    *,
    api_key: str,
    first_line: str,
    lang: str,
    tts_provider: str,
    tts_voice: str,
    tts_model: str,
    gemini_model: str,
    voice_per_lang: dict[str, str],
) -> None:
    """Guaranteed attempt for the critical first dialogue line."""
    from greeting_cache import prebake_all_greetings

    await prebake_all_greetings(
        api_key,
        voice_override=tts_voice,
        provider=tts_provider,
        model=tts_model,
        extra_greetings={lang: first_line},
        extra_session_lines=[],
        lang_preset="tinglish",  # langs overridden below
        languages=[lang],
        voice_per_lang=voice_per_lang or None,
        gemini_voice=tts_voice,
        gemini_model=gemini_model,
        disk_only=not api_key,
    )


async def _run_prebake(
    *,
    ship_config: dict[str, Any],
    cache_dir: Path,
    host_cache: Path,
) -> dict[str, Any]:
    """Prebake into an isolated cache_dir (does not pollute host cache permanently)."""
    import greeting_cache as gc
    from greeting_cache import (
        _collect_prebake_items,
        languages_for_preset,
        prebake_all_greetings,
        session_lines_from_config,
    )
    from language_router import get_default_turn_language, resolve_lang_preset

    original_dir = gc.DISK_CACHE_DIR
    gc.DISK_CACHE_DIR = cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "ok": False,
        "provider": None,
        "voice": None,
        "model": None,
        "first_line": None,
        "pcm_files": [],
        "items_attempted": 0,
        "error": None,
        "disk_only": False,
        "host_seeded": 0,
    }

    try:
        preset = resolve_lang_preset(ship_config.get("lang_preset"), ship_config)
        tts_provider = str(ship_config.get("tts_provider") or "cartesia").strip().lower()
        tts_voice = str(ship_config.get("tts_voice") or "").strip()
        cartesia_model = str(ship_config.get("cartesia_tts_model") or "sonic-3.5").strip()
        gemini_model = str(
            ship_config.get("gemini_tts_model") or "gemini-3.1-flash-tts-preview"
        ).strip()
        tts_model = cartesia_model if tts_provider == "cartesia" else gemini_model

        api_key = _resolve_api_key(tts_provider)
        disk_only = not bool(api_key)

        voice_per_lang: dict[str, str] = {}
        if tts_provider == "cartesia":
            try:
                from cartesia_tts import cartesia_prebake_voice_map

                voice_per_lang = cartesia_prebake_voice_map(preset) or {}
            except Exception as exc:
                logger.warning("[SHIP-PREBAKE] voice map failed: %s", exc)
            if not tts_voice and voice_per_lang:
                tts_voice = next(iter(voice_per_lang.values()))

        first_line = str(ship_config.get("first_line") or "").strip()
        default_lang = get_default_turn_language(preset, ship_config)
        extra_greetings = {default_lang: first_line} if first_line else None
        session_lines = session_lines_from_config(ship_config)
        active_langs = languages_for_preset(preset)

        items = _collect_prebake_items(
            extra_greetings=extra_greetings,
            extra_session_lines=session_lines,
            lang_preset=preset,
            languages=active_langs,
        )

        # Critical path items first: first_line + session
        critical: list[tuple[str, str, str]] = []
        if first_line:
            critical.append((default_lang, first_line, "greeting"))
        for lang, text in session_lines:
            critical.append((lang, text, "session"))

        report.update({
            "provider": tts_provider,
            "voice": tts_voice,
            "model": tts_model,
            "first_line": first_line[:200] if first_line else None,
            "lang_preset": preset,
            "languages": active_langs,
            "items_attempted": len(items),
            "disk_only": disk_only,
            "session_lines": len(session_lines),
            "has_api_key": bool(api_key),
        })

        # 1) Seed from host cache (works even when Cartesia billing fails)
        seeded = _seed_from_host_cache(
            host_cache=host_cache,
            ship_cache=cache_dir,
            items=items,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            tts_model=tts_model,
            voice_per_lang=voice_per_lang,
        )
        report["host_seeded"] = seeded
        if seeded:
            logger.info("[SHIP-PREBAKE] Seeded %d PCM from host cache", seeded)

        # 2) API prebake (full set) when key present
        if api_key:
            try:
                await prebake_all_greetings(
                    api_key,
                    voice_override=tts_voice,
                    provider=tts_provider,
                    model=tts_model,
                    extra_greetings=extra_greetings,
                    extra_session_lines=session_lines,
                    lang_preset=preset,
                    languages=active_langs,
                    voice_per_lang=voice_per_lang or None,
                    gemini_voice=tts_voice,
                    gemini_model=gemini_model,
                    disk_only=False,
                )
            except Exception as exc:
                logger.warning("[SHIP-PREBAKE] full prebake error: %s", exc)
                report["error"] = str(exc)
            # If first line still missing, try isolated first-line bake
            pcm_after = list(cache_dir.glob("*.pcm"))
            if first_line and not pcm_after:
                try:
                    await _prebake_first_line_only(
                        api_key=api_key,
                        first_line=first_line,
                        lang=default_lang,
                        tts_provider=tts_provider,
                        tts_voice=tts_voice,
                        tts_model=tts_model,
                        gemini_model=gemini_model,
                        voice_per_lang=voice_per_lang,
                    )
                except Exception as exc:
                    logger.warning("[SHIP-PREBAKE] first-line only failed: %s", exc)
        else:
            report["error"] = (
                "No TTS API key on platform host — PCM only from host cache seed. "
                "Client must run: python3 scripts/bootstrap_client.py after filling .env"
            )
            logger.warning("[SHIP-PREBAKE] %s", report["error"])

        pcm_files = sorted(cache_dir.glob("*.pcm"))
        report["pcm_files"] = [p.name for p in pcm_files]
        report["pcm_count"] = len(pcm_files)
        report["ok"] = len(pcm_files) > 0
        if first_line and not pcm_files:
            report["error"] = (
                report.get("error")
                or "Prebake produced 0 PCM — check TTS billing / voice id; "
                "client bootstrap will retry"
            )
            report["ok"] = False

        index = {
            "first_line": first_line,
            "provider": tts_provider,
            "voice": tts_voice,
            "model": tts_model,
            "lang_preset": preset,
            "pcm_count": len(pcm_files),
            "host_seeded": seeded,
            "files": [p.name for p in pcm_files],
            "critical_texts": [t for _, t, _ in critical],
            "items": [
                {"lang": lang, "kind": kind, "text": text[:120]}
                for lang, text, kind in items
            ],
        }
        (cache_dir / "PREWARM_INDEX.json").write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return report
    except Exception as exc:
        logger.exception("[SHIP-PREBAKE] failed")
        report["error"] = str(exc)
        report["ok"] = False
        return report
    finally:
        gc.DISK_CACHE_DIR = original_dir


def _run_prebake_blocking(**kwargs: Any) -> dict[str, Any]:
    """Run the async prebake to completion from any context.

    The /platform "Create codebase" route is async, so this is often invoked
    from a thread that already has a running event loop — where asyncio.run()
    raises and the prebake silently never runs (0 PCM shipped). Detect that and
    run the coroutine on its own loop in a worker thread. The CLI ship path has
    no running loop and runs inline.
    """
    def _worker() -> dict[str, Any]:
        return asyncio.run(_run_prebake(**kwargs))

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _worker()  # no running loop — safe inline
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_worker).result()


def prebake_for_ship(ship_config: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, Any]]:
    """
    Returns (rel_path → bytes for ZIP, prebake_report).

    Always safe to call — if no API key and no host cache hits, returns empty
    PCM map + bootstrap instructions.
    """
    root = Path(__file__).resolve().parents[1]
    host_cache = root / "data" / "greeting_pcm_cache"

    with tempfile.TemporaryDirectory(prefix="speaksy-ship-prebake-") as tmp:
        cache_dir = Path(tmp) / "greeting_pcm_cache"
        report = _run_prebake_blocking(
            ship_config=ship_config,
            cache_dir=cache_dir,
            host_cache=host_cache,
        )
        files: dict[str, bytes] = {}
        if cache_dir.is_dir():
            for path in cache_dir.rglob("*"):
                if not path.is_file():
                    continue
                rel = f"data/greeting_pcm_cache/{path.relative_to(cache_dir).as_posix()}"
                try:
                    files[rel] = path.read_bytes()
                except OSError:
                    continue
        return files, report
