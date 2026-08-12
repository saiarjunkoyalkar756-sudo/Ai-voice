"""Tiered LLM TTFT guard tests."""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from llm_tiered_guard import tiered_llm_stream


class _Chunk:
    def __init__(self, text: str = ""):
        self.delta = type("D", (), {"content": text, "tool_calls": None})()


async def _slow_stream(delay: float, text: str = "ok"):
    await asyncio.sleep(delay)
    yield _Chunk(text)


async def _fast_stream(text: str = "ok"):
    yield _Chunk(text)


@pytest.mark.asyncio
async def test_tiered_passes_through_fast_stream():
    out = []
    async for c in tiered_llm_stream(
        lambda: _fast_stream("hello"),
        retry_at_ms=200,
        hard_cap_ms=500,
        fallback=lambda: "fallback",
    ):
        out.append(c)
    assert len(out) == 1
    assert out[0].delta.content == "hello"


@pytest.mark.asyncio
async def test_tiered_retries_then_succeeds():
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        if calls["n"] == 1:
            return _slow_stream(0.25, "late")
        return _fast_stream("retry-ok")

    out = []
    async for c in tiered_llm_stream(
        factory,
        retry_at_ms=100,
        hard_cap_ms=500,
        fallback=lambda: "fallback",
    ):
        out.append(c)
    assert calls["n"] == 2
    assert out[0].delta.content == "retry-ok"


@pytest.mark.asyncio
async def test_tiered_hard_cap_fallback():
    out = []
    async for c in tiered_llm_stream(
        lambda: _slow_stream(2.0, "never"),
        retry_at_ms=50,
        hard_cap_ms=120,
        fallback=lambda: "canned",
    ):
        out.append(c)
    assert out == ["canned"]