"""
Extracted LLM stream helpers (plan 01-001 partial — llm_node module).

VoiceAgentAssistant.llm_node remains the LiveKit hook; pure streaming policy
lives here for unit tests without Agent subclass.
"""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

logger = logging.getLogger("speaksy-engine")


def apply_turn_token_cap(model_settings: Any, live_config: dict[str, Any]) -> None:
    turn_cap = live_config.get("_turn_max_completion_tokens")
    if not turn_cap or model_settings is None:
        return
    try:
        if hasattr(model_settings, "max_completion_tokens"):
            model_settings.max_completion_tokens = int(turn_cap)
        elif isinstance(model_settings, dict):
            model_settings["max_completion_tokens"] = int(turn_cap)
    except Exception:
        pass


async def stream_with_ttft_metrics(
    stream: AsyncIterator[Any],
    *,
    live_config: dict[str, Any],
    on_first_token: Callable[[float], None] | None = None,
) -> AsyncIterator[Any]:
    """Wrap an LLM chunk stream; record TTFT once."""
    start = time.perf_counter()
    first = True
    async for chunk in stream:
        if first:
            first = False
            elapsed_ms = (time.perf_counter() - start) * 1000
            if on_first_token:
                on_first_token(elapsed_ms)
            metrics = live_config.get("_turn_metrics")
            if metrics is not None:
                try:
                    metrics.note_llm_ttft(elapsed_ms)
                except Exception:
                    pass
            warn_ms = float(live_config.get("llm_ttft_warn_ms", 800.0))
            if elapsed_ms >= warn_ms:
                logger.warning(
                    "[LLM-TTFT] slow first token %.0fms (warn>=%.0f)",
                    elapsed_ms,
                    warn_ms,
                )
        yield chunk


def build_tiered_protected_stream(
    default_stream_factory: Callable[[], AsyncIterator[Any]],
    *,
    live_config: dict[str, Any],
    fallback: Callable[[], Any],
) -> AsyncIterator[Any]:
    """Return async generator of protected tiered LLM chunks."""

    async def _gen() -> AsyncIterator[Any]:
        from circuit_breaker import protected_async_iter
        from engine.ttft_policy import apply_ttft_defaults
        from llm_tiered_guard import tiered_llm_stream

        ttft = apply_ttft_defaults(live_config)
        tiered = tiered_llm_stream(
            default_stream_factory,
            retry_at_ms=ttft.retry_ms,
            hard_cap_ms=ttft.hard_cap_ms,
            fallback=fallback,
            service_name="gemini_llm",
        )
        async for chunk in protected_async_iter(
            "gemini_llm",
            tiered,
            fallback=fallback,
            sla_ms=ttft.hard_cap_ms,
        ):
            yield chunk

    return _gen()
