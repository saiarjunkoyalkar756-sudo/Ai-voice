"""
Partial STT stability tracker — endpointing clock + speculative overlap metrics.

When a Soniox partial is unchanged for ~250ms, treat it as "caller stopped speaking"
and start the voice-to-voice TTFA clock (before is_final). LiveKit preemptive_generation
overlaps the remaining endpoint wait with LLM work.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

logger = logging.getLogger("inbound-voice-agent")

DEFAULT_STABLE_PARTIAL_MS = 250
_DEFAULT_MATCH_THRESHOLD = 0.90

_DIGITS_RE = re.compile(r"\d+")
_NAME_FRAGMENT_RE = re.compile(
    r"\b\d+\s*(?:bhk|cr|crore|lakh|sq\.?\s*ft|emi)\b",
    re.I,
)


def _stable_ms(live_config: dict | None) -> int:
    try:
        return max(
            150,
            min(
                int((live_config or {}).get("speculative_partial_stable_ms", DEFAULT_STABLE_PARTIAL_MS)),
                600,
            ),
        )
    except (TypeError, ValueError):
        return DEFAULT_STABLE_PARTIAL_MS


def _match_threshold(live_config: dict | None) -> float:
    try:
        return float((live_config or {}).get("speculative_partial_match_threshold", _DEFAULT_MATCH_THRESHOLD))
    except (TypeError, ValueError):
        return _DEFAULT_MATCH_THRESHOLD


def _enabled(live_config: dict | None) -> bool:
    return bool((live_config or {}).get("speculative_partial_enabled", True))


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def normalized_match_ratio(partial: str, final: str) -> float:
    """Token overlap ratio between stable partial and final transcript."""
    a = _normalize(partial).split()
    b = _normalize(final).split()
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    overlap = len(sa & sb)
    return overlap / max(len(sa), len(sb))


def speculative_partial_unsafe(partial: str) -> bool:
    """Skip speculation when partial may still be mid-number/name."""
    text = (partial or "").strip()
    if not text:
        return True
    if _DIGITS_RE.search(text) and not text.rstrip().endswith((".", "?", "!", ",")):
        tail = text.split()[-1] if text.split() else ""
        if tail and tail[-1].isdigit():
            return True
    if _NAME_FRAGMENT_RE.search(text):
        return True
    return False


def _cancel_stable_task(cfg: dict) -> None:
    task = cfg.pop("_partial_stable_task", None)
    if task is not None and not task.done():
        task.cancel()


def reset_partial_turn_state(live_config: dict | None, *, reason: str = "") -> None:
    cfg = live_config or {}
    _cancel_stable_task(cfg)
    cfg.pop("_partial_last_text", None)
    cfg.pop("_partial_stable_since", None)
    cfg.pop("_ttfa_clock_armed", None)
    cfg.pop("_speculative_partial_text", None)
    if reason:
        logger.debug("[PARTIAL-TURN] reset (%s)", reason)


async def _arm_stable_partial(
    cfg: dict,
    text: str,
    *,
    stable_ms: int,
    quality_scorer: Any | None,
) -> None:
    await asyncio.sleep(stable_ms / 1000.0)
    if cfg.get("_partial_last_text") != text:
        return
    if speculative_partial_unsafe(text):
        logger.debug("[PARTIAL-TURN] skip stable partial (unsafe): %r", text[:80])
        return

    if not cfg.get("_ttfa_clock_armed"):
        cfg["_ttfa_clock_armed"] = True
        if quality_scorer is not None:
            quality_scorer.record_user_speech_finished()
        logger.debug("[PARTIAL-TURN] TTFA clock started (stable %dms): %r", stable_ms, text[:80])

    cfg["_speculative_partial_text"] = text
    cfg["_speculative_partial_stable_ms"] = stable_ms
    journal = cfg.setdefault("_speculative_partial_journal", [])
    journal.append(
        {
            "event": "stable_partial",
            "text": text[:200],
            "stable_ms": stable_ms,
            "ts": time.time(),
        }
    )


def on_stt_partial(
    live_config: dict | None,
    transcript: str,
    *,
    quality_scorer: Any | None = None,
    agent_is_speaking: bool = False,
) -> None:
    """Call on every non-final STT transcript."""
    if not _enabled(live_config) or agent_is_speaking:
        return

    cfg = live_config or {}
    text = (transcript or "").strip()
    if not text:
        return

    prev = cfg.get("_partial_last_text", "")
    if text == prev:
        return

    cfg["_partial_last_text"] = text
    cfg["_partial_stable_since"] = time.perf_counter()
    _cancel_stable_task(cfg)

    stable_ms = _stable_ms(cfg)
    task = asyncio.create_task(
        _arm_stable_partial(cfg, text, stable_ms=stable_ms, quality_scorer=quality_scorer),
        name="partial_stable_ttfa",
    )
    cfg["_partial_stable_task"] = task


def on_stt_final(
    live_config: dict | None,
    final_transcript: str,
    *,
    quality_scorer: Any | None = None,
) -> dict[str, Any]:
    """
    Call when is_final arrives. Arms STT-final timestamp; records partial match stats.
    Does NOT start TTFA clock (that happens on stable partial).
    """
    cfg = live_config or {}
    _cancel_stable_task(cfg)

    final = (final_transcript or "").strip()
    partial = str(cfg.get("_speculative_partial_text") or cfg.get("_partial_last_text") or "")

    if quality_scorer is not None:
        if not cfg.get("_ttfa_clock_armed"):
            quality_scorer.record_user_speech_finished()
            cfg["_ttfa_clock_armed"] = True
        quality_scorer.record_user_final_transcript()

    ratio = normalized_match_ratio(partial, final) if partial and final else 0.0
    threshold = _match_threshold(cfg)
    hit = ratio >= threshold and bool(partial)
    stats = {
        "partial_text": partial[:120],
        "final_text": final[:120],
        "match_ratio": round(ratio, 3),
        "spec_hit": hit,
        "threshold": threshold,
    }
    journal = cfg.setdefault("_speculative_partial_journal", [])
    journal.append({"event": "final", **stats, "ts": time.time()})

    metrics = cfg.setdefault("_speculative_partial_metrics", {"finals": 0, "hits": 0})
    metrics["finals"] = int(metrics.get("finals", 0)) + 1
    if hit:
        metrics["hits"] = int(metrics.get("hits", 0)) + 1

    cfg["_speculative_partial_last"] = stats
    _cancel_stable_task(cfg)
    cfg.pop("_partial_last_text", None)
    cfg.pop("_partial_stable_since", None)
    cfg.pop("_ttfa_clock_armed", None)
    cfg.pop("_speculative_partial_text", None)
    return stats


def get_speculative_partial_metrics(live_config: dict | None) -> dict[str, Any]:
    cfg = live_config or {}
    m = dict(cfg.get("_speculative_partial_metrics") or {})
    finals = int(m.get("finals", 0))
    hits = int(m.get("hits", 0))
    return {
        "enabled": _enabled(cfg),
        "stable_ms": _stable_ms(cfg),
        "finals": finals,
        "hits": hits,
        "hit_rate": round(hits / finals, 3) if finals else 0.0,
        "last": dict(cfg.get("_speculative_partial_last") or {}),
    }