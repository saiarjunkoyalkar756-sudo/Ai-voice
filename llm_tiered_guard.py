"""
Tiered LLM TTFT guard — hard cap on first-token latency.

Stages (Operation Sub-Second Phase 3.2):
  t+1500ms no first token → cancel stream, one retry
  t+2300ms still no token → canned fallback line, log incident

Filler audio at t+700ms is handled separately by filler_injection.py.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

logger = logging.getLogger("inbound-voice-agent")

DEFAULT_RETRY_AT_MS = 1500.0
DEFAULT_HARD_CAP_MS = 2300.0


def _chunk_has_content(chunk: Any) -> bool:
    delta = getattr(chunk, "delta", None)
    if delta is None:
        return bool(chunk)
    content = getattr(delta, "content", None)
    if content:
        return True
    tool_calls = getattr(delta, "tool_calls", None)
    return bool(tool_calls)


async def _close_stream(stream: Any) -> None:
    if hasattr(stream, "aclose"):
        try:
            await stream.aclose()
        except Exception:
            pass


async def _first_content_chunk(
    stream: AsyncIterator[Any],
    *,
    timeout_sec: float,
) -> tuple[Any | None, AsyncIterator[Any] | None]:
    """Read until a content-bearing chunk or timeout. Returns (chunk, tail_iter)."""
    if timeout_sec <= 0:
        await _close_stream(stream)
        return None, None

    deadline = time.perf_counter() + timeout_sec
    iterator = stream.__aiter__()
    pending: list[Any] = []

    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            await _close_stream(stream)
            return None, None
        try:
            chunk = await asyncio.wait_for(iterator.__anext__(), timeout=remaining)
        except StopAsyncIteration:
            await _close_stream(stream)
            return None, None
        except asyncio.TimeoutError:
            await _close_stream(stream)
            return None, None

        if _chunk_has_content(chunk):

            async def _tail() -> AsyncIterator[Any]:
                for p in pending:
                    yield p
                yield chunk
                async for rest in iterator:
                    yield rest

            return chunk, _tail()

        pending.append(chunk)


async def tiered_llm_stream(
    stream_factory: Callable[[], AsyncIterator[Any]],
    *,
    retry_at_ms: float = DEFAULT_RETRY_AT_MS,
    hard_cap_ms: float = DEFAULT_HARD_CAP_MS,
    fallback: Callable[[], Any],
    service_name: str = "gemini_llm",
) -> AsyncIterator[Any]:
    """
    Wrap an LLM async generator with tiered first-token timeouts.

    ``stream_factory`` is called once for the initial attempt and again on retry.
    """
    start = time.perf_counter()
    retried = False

    while True:
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms >= hard_cap_ms:
            break

        attempt_limit_ms = retry_at_ms if not retried else hard_cap_ms
        attempt_budget_ms = min(attempt_limit_ms - elapsed_ms, hard_cap_ms - elapsed_ms)
        if attempt_budget_ms <= 0:
            break

        _first, tail = await _first_content_chunk(
            stream_factory(),
            timeout_sec=attempt_budget_ms / 1000.0,
        )
        if tail is not None:
            async for chunk in tail:
                yield chunk
            return

        if not retried:
            retried = True
            logger.warning(
                "[LLM-TIERED] %s: no first token in %.0fms — retrying once",
                service_name,
                attempt_budget_ms,
            )
            continue
        break

    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.error(
        "[LLM-TIERED] %s: hard cap %.0fms exceeded (%.0fms) — canned fallback",
        service_name,
        hard_cap_ms,
        elapsed_ms,
    )
    fb = fallback()
    if asyncio.iscoroutine(fb):
        fb = await fb
    if fb is not None:
        if isinstance(fb, str):
            yield fb
        else:
            for item in fb:
                yield item