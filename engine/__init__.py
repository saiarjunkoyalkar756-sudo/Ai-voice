"""
Voicely Conversation Engine package.

Implements the fused architecture from VOICELY_ENGINE_MASTER_PLAN:
  transport → stt → ConversationEngine → llm → tts → metrics tail

agent.py remains the LiveKit worker host; business turn logic and
observability contracts live here so they are testable without LiveKit.
"""
from __future__ import annotations

from engine.active_calls import ActiveCallRegistry, get_registry
from engine.conversation_engine import ConversationEngine
from engine.metrics.turn_metrics import TurnMetrics, TurnMetricsCollector, TurnStage
from engine.pinned_config import pin_call_config, config_hash
from engine.turn_result import TurnResult
from engine.tracing import bind_trace, get_trace_id, span
from engine.voicemail import classify_call_outcome

__all__ = [
    "ActiveCallRegistry",
    "ConversationEngine",
    "TurnMetrics",
    "TurnMetricsCollector",
    "TurnStage",
    "TurnResult",
    "pin_call_config",
    "config_hash",
    "get_registry",
    "bind_trace",
    "get_trace_id",
    "span",
    "classify_call_outcome",
]

__version__ = "1.2.0"
