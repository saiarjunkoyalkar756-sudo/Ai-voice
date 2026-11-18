"""
Dream pipeline ↔ next-call injection bridge (plan 02-008).

After dream consolidation, push hot context for the next inbound.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("voicely-engine")


async def run_dream_and_hot_context(
    phone: str,
    memory_dir: str | Path,
    *,
    profile: Any = None,
) -> None:
    if not phone or phone in ("unknown", "anonymous"):
        return
    try:
        from re_voice_memory.dream import run_dream_pipeline

        await run_dream_pipeline(phone, memory_dir)
    except Exception as exc:
        logger.warning("[DREAM] pipeline failed phone=%s: %s", phone[-4:], exc)
        return

    try:
        from re_voice_memory.kv_store import set_lead_hot_context

        if profile is not None:
            ok = await set_lead_hot_context(phone, profile)
            logger.info("[DREAM] hot_context phone=…%s ok=%s", phone[-4:], ok)
    except Exception as exc:
        logger.debug("[DREAM] hot_context skip: %s", exc)
