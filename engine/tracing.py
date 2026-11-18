"""
Lightweight distributed-style tracing (plan 06-003).

No hard dependency on Langfuse/OTel — always-on structured trace context
propagated via contextvars + log fields. Optional export hooks later.
"""
from __future__ import annotations

import contextvars
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator

_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("voicely_trace_id", default="")
_span_stack: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "voicely_span_stack", default=()
)

logger = logging.getLogger("voicely.trace")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    return _trace_id.get() or ""


def bind_trace(trace_id: str | None = None) -> str:
    tid = trace_id or new_trace_id()
    _trace_id.set(tid)
    return tid


@dataclass
class Span:
    name: str
    trace_id: str
    t0: float = field(default_factory=time.perf_counter)
    attrs: dict[str, Any] = field(default_factory=dict)

    def end(self, **attrs: Any) -> dict[str, Any]:
        ms = round((time.perf_counter() - self.t0) * 1000, 2)
        payload = {
            "trace_id": self.trace_id,
            "span": self.name,
            "duration_ms": ms,
            **self.attrs,
            **attrs,
        }
        logger.info(
            "[TRACE] trace=%s span=%s ms=%.1f %s",
            self.trace_id,
            self.name,
            ms,
            {k: v for k, v in payload.items() if k not in ("trace_id", "span", "duration_ms")},
        )
        return payload


class span:
    """Context manager: with span('llm_ttft', model='x'): ..."""

    def __init__(self, name: str, **attrs: Any) -> None:
        self.name = name
        self.attrs = attrs
        self._span: Span | None = None
        self._token = None

    def __enter__(self) -> Span:
        tid = get_trace_id() or bind_trace()
        self._span = Span(name=self.name, trace_id=tid, attrs=dict(self.attrs))
        stack = _span_stack.get()
        self._token = _span_stack.set(stack + (self.name,))
        return self._span

    def __exit__(self, *exc: Any) -> None:
        if self._span:
            if exc[0] is not None:
                self._span.end(error=str(exc[1] or exc[0]))
            else:
                self._span.end()
        if self._token is not None:
            _span_stack.reset(self._token)


def call_trace_fields() -> dict[str, str]:
    return {"trace_id": get_trace_id(), "span_path": "/".join(_span_stack.get())}
