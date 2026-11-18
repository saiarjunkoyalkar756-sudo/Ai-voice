"""
Explicit pipeline stage model (plan 01-002).

Not a new framework — a documented ordered contract the rest of the engine
implements via TurnMetricsCollector.
"""
from __future__ import annotations

from engine.metrics.turn_metrics import TurnStage

PIPELINE_STAGES: tuple[TurnStage, ...] = (
    TurnStage.STT_FINAL,
    TurnStage.TURN_INJECT,
    TurnStage.LLM_TTFT,
    TurnStage.REPLY_BUFFER,
    TurnStage.TTS_TTFA,
    TurnStage.FIRST_AUDIO_OUT,
)

STAGE_DIAGRAM = """
Voicely turn pipeline (LiveKit Agents SDK host):

  [PSTN/WebRTC] → STT final
       → ConversationEngine (identity · inject waves · length policy)
       → LLM TTFT (tiered guard + circuit breaker)
       → reply buffer / sentence chunker
       → TTS first audio frame
       → transport out
       → TurnMetricsCollector.flush → call_logs.turn_metrics

Stages are timed independently so p50/p95 waterfalls are truthful.
"""


def stage_names() -> list[str]:
    return [s.value for s in PIPELINE_STAGES]
