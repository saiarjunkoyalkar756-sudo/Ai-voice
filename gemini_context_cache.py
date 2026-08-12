"""
Optional Gemini explicit context cache warmup (google-genai native SDK).

Implicit prefix caching is the primary path (stable compiled prompt + stage tools).
This module pre-creates a cachedContent artifact when GEMINI_CONTEXT_CACHE=1.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger("inbound-voice-agent")


def context_cache_enabled() -> bool:
    return os.environ.get("GEMINI_CONTEXT_CACHE", "1").strip().lower() in ("1", "true", "yes", "on")


async def warm_gemini_context_cache(
    live_config: dict | None,
    *,
    model: str,
    system_prompt: str,
    ttl_sec: int = 3600,
) -> str | None:
    """Best-effort explicit cache; returns cache resource name or None."""
    if not context_cache_enabled():
        return None
    text = (system_prompt or "").strip()
    if not text:
        return None

    key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        return None

    cfg = live_config or {}
    existing = cfg.get("_gemini_cache_name")
    if existing:
        return str(existing)

    try:
        from google import genai as google_genai
        from google.genai import types
    except ImportError:
        logger.debug("[GEMINI-CACHE] google-genai not installed — skip explicit cache")
        return None

    try:
        client = google_genai.Client(api_key=key)
        cache = await asyncio.to_thread(
            client.caches.create,
            model=model,
            config=types.CreateCachedContentConfig(
                display_name=f"speaksy-{cfg.get('lang_preset', 'tinglish')}",
                system_instruction=text,
                ttl=f"{max(300, ttl_sec)}s",
            ),
        )
        name = getattr(cache, "name", None)
        if name:
            cfg["_gemini_cache_name"] = name
            logger.info("[GEMINI-CACHE] Explicit cache ready: %s", name)
            return str(name)
    except Exception as exc:
        logger.warning("[GEMINI-CACHE] Warmup failed (implicit cache still active): %s", exc)
    return None