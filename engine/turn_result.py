"""TurnResult contract between ConversationEngine and LLM/TTS (plan 02-002)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnResult:
    """Structured outcome of one user turn before LLM/TTS runs."""

    system_messages: list[str] = field(default_factory=list)
    skip_llm: bool = False
    scripted_reply: str | None = None
    max_completion_tokens: int | None = None
    tts_language: str | None = None
    speculative_hint: str | None = None
    identity_trap: bool = False
    deal_stage: str | None = None
    inject_ms: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "system_messages": list(self.system_messages),
            "skip_llm": self.skip_llm,
            "scripted_reply": self.scripted_reply,
            "max_completion_tokens": self.max_completion_tokens,
            "tts_language": self.tts_language,
            "speculative_hint": self.speculative_hint,
            "identity_trap": self.identity_trap,
            "deal_stage": self.deal_stage,
            "inject_ms": self.inject_ms,
            "extra": dict(self.extra),
        }
