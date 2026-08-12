"""
Turn metrics schema — truthful per-stage latency (plans 06-001, 01-002, 03-001).

Every agent turn should produce one TurnMetrics row with:
  stt_final → turn_inject → llm_ttft → reply_buffer → tts_ttfa → first_audio_out

Instrumentation overhead target: <1ms.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterator


class TurnStage(str, Enum):
    STT_FINAL = "stt_final"
    TURN_INJECT = "turn_inject"
    LLM_TTFT = "llm_ttft"
    REPLY_BUFFER = "reply_buffer"
    TTS_TTFA = "tts_ttfa"
    FIRST_AUDIO_OUT = "first_audio_out"


_STAGE_ORDER = list(TurnStage)


@dataclass
class TurnMetrics:
    """One row per user turn — serializable to call_logs.turn_metrics JSONB."""

    turn: int = 0
    room_id: str = ""
    transcript_chars: int = 0
    stages_ms: dict[str, float] = field(default_factory=dict)
    e2e_ms: float | None = None
    ttfa_server_ms: float | None = None
    reply_cache_hit: bool = False
    skip_llm: bool = False
    identity_trap: bool = False
    max_completion_tokens: int | None = None
    tts_language: str | None = None
    adaptive_endpoint_ms: float | None = None
    config_hash: str | None = None
    deal_stage: str | None = None
    errors: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def mark(self, stage: TurnStage | str, ms: float) -> None:
        key = stage.value if isinstance(stage, TurnStage) else str(stage)
        self.stages_ms[key] = round(float(ms), 2)

    def recompute_e2e(self) -> float | None:
        """Sum known stages when explicit e2e not set."""
        if self.e2e_ms is not None:
            return self.e2e_ms
        total = 0.0
        any_stage = False
        for st in _STAGE_ORDER:
            if st.value in self.stages_ms:
                total += self.stages_ms[st.value]
                any_stage = True
        if any_stage:
            self.e2e_ms = round(total, 2)
        return self.e2e_ms

    def to_row(self) -> dict[str, Any]:
        self.recompute_e2e()
        row = asdict(self)
        # Flatten stages for legacy consumers
        row["stt_ms"] = self.stages_ms.get(TurnStage.STT_FINAL.value)
        row["inject_ms"] = self.stages_ms.get(TurnStage.TURN_INJECT.value)
        row["llm_ms"] = self.stages_ms.get(TurnStage.LLM_TTFT.value)
        row["buffer_ms"] = self.stages_ms.get(TurnStage.REPLY_BUFFER.value)
        row["tts_ms"] = self.stages_ms.get(TurnStage.TTS_TTFA.value)
        row["ttfa_server_ms"] = self.ttfa_server_ms or self.e2e_ms
        row["e2e_ms"] = self.e2e_ms
        return row


class TurnTimer:
    """Context manager: measures wall ms for one stage."""

    __slots__ = ("_collector", "_stage", "_t0")

    def __init__(self, collector: "TurnMetricsCollector", stage: TurnStage) -> None:
        self._collector = collector
        self._stage = stage
        self._t0 = 0.0

    def __enter__(self) -> "TurnTimer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc: Any) -> None:
        ms = (time.perf_counter() - self._t0) * 1000.0
        self._collector.mark(self._stage, ms)


class TurnMetricsCollector:
    """Per-call collector; one TurnMetrics object per user turn."""

    def __init__(self, *, room_id: str = "", config_hash: str | None = None) -> None:
        self.room_id = room_id
        self.config_hash = config_hash
        self._current: TurnMetrics | None = None
        self._history: list[TurnMetrics] = []
        self._turn_wall_t0: float | None = None

    def begin_turn(
        self,
        turn: int,
        *,
        transcript: str = "",
        adaptive_endpoint_ms: float | None = None,
        deal_stage: str | None = None,
    ) -> TurnMetrics:
        # Close previous incomplete turn
        if self._current is not None:
            self.end_turn()
        self._turn_wall_t0 = time.perf_counter()
        m = TurnMetrics(
            turn=turn,
            room_id=self.room_id,
            transcript_chars=len(transcript or ""),
            adaptive_endpoint_ms=adaptive_endpoint_ms,
            config_hash=self.config_hash,
            deal_stage=deal_stage,
        )
        # Endpointing delay is part of felt STT-final lag (plan 03-001)
        if adaptive_endpoint_ms is not None:
            m.mark(TurnStage.STT_FINAL, float(adaptive_endpoint_ms))
        self._current = m
        return m

    @property
    def current(self) -> TurnMetrics | None:
        return self._current

    def mark(self, stage: TurnStage | str, ms: float) -> None:
        if self._current is not None:
            self._current.mark(stage, ms)

    def timer(self, stage: TurnStage) -> TurnTimer:
        return TurnTimer(self, stage)

    def note_llm_ttft(self, ms: float) -> None:
        self.mark(TurnStage.LLM_TTFT, ms)

    def note_inject(self, ms: float) -> None:
        self.mark(TurnStage.TURN_INJECT, ms)

    def note_tts_ttfa(self, ms: float, *, reply_cache_hit: bool = False) -> None:
        self.mark(TurnStage.TTS_TTFA, ms)
        if self._current is not None:
            self._current.reply_cache_hit = reply_cache_hit
            # Prefer sum of timed components when wall-clock is sub-ms (unit tests /
            # same-tick instrumentation). Live calls still get real wall e2e.
            component_keys = (
                TurnStage.STT_FINAL.value,
                TurnStage.TURN_INJECT.value,
                TurnStage.LLM_TTFT.value,
                TurnStage.REPLY_BUFFER.value,
                TurnStage.TTS_TTFA.value,
            )
            component_sum = sum(
                float(self._current.stages_ms[k])
                for k in component_keys
                if k in self._current.stages_ms
            )
            wall = 0.0
            if self._turn_wall_t0 is not None:
                wall = (time.perf_counter() - self._turn_wall_t0) * 1000.0
            e2e = max(wall, component_sum)
            self._current.ttfa_server_ms = round(e2e, 2)
            self._current.e2e_ms = round(e2e, 2)
            self.mark(TurnStage.FIRST_AUDIO_OUT, e2e)

    def note_reply_buffer(self, ms: float) -> None:
        self.mark(TurnStage.REPLY_BUFFER, ms)

    def note_skip_llm(self, *, identity_trap: bool = False) -> None:
        if self._current is not None:
            self._current.skip_llm = True
            self._current.identity_trap = identity_trap

    def note_tokens(self, n: int | None) -> None:
        if self._current is not None and n is not None:
            self._current.max_completion_tokens = int(n)

    def note_tts_language(self, lang: str | None) -> None:
        if self._current is not None and lang:
            self._current.tts_language = lang

    def end_turn(self) -> TurnMetrics | None:
        m = self._current
        if m is None:
            return None
        m.recompute_e2e()
        self._history.append(m)
        self._current = None
        self._turn_wall_t0 = None
        return m

    def rows(self) -> list[dict[str, Any]]:
        if self._current is not None:
            self.end_turn()
        return [m.to_row() for m in self._history]

    def export(self) -> dict[str, Any]:
        rows = self.rows()
        from turn_latency import summarize_turn_latencies, reply_cache_metrics

        return {
            "schema": "speaksy.turn_metrics.v1",
            "room_id": self.room_id,
            "config_hash": self.config_hash,
            "turns": rows,
            "summary": summarize_turn_latencies(rows),
            "reply_cache_metrics": reply_cache_metrics(rows),
            "stage_p50": _stage_percentiles(rows, 50),
            "stage_p95": _stage_percentiles(rows, 95),
        }


def _stage_percentiles(rows: list[dict[str, Any]], pct: float) -> dict[str, float]:
    from turn_latency import _percentile

    out: dict[str, float] = {}
    for st in TurnStage:
        vals: list[float] = []
        for r in rows:
            stages = r.get("stages_ms") or {}
            if st.value in stages:
                try:
                    vals.append(float(stages[st.value]))
                except (TypeError, ValueError):
                    pass
            # legacy flat keys
            legacy = {
                TurnStage.STT_FINAL: "stt_ms",
                TurnStage.TURN_INJECT: "inject_ms",
                TurnStage.LLM_TTFT: "llm_ms",
                TurnStage.REPLY_BUFFER: "buffer_ms",
                TurnStage.TTS_TTFA: "tts_ms",
            }.get(st)
            if legacy and r.get(legacy) is not None:
                try:
                    vals.append(float(r[legacy]))
                except (TypeError, ValueError):
                    pass
        if vals:
            out[st.value] = _percentile(vals, pct)
    return out
