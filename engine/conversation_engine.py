"""
ConversationEngine — sales-aware turn orchestration (plans 02-001, 02-002, 02-006, 02-007).

LiveKit-free: only strings/dicts/dataclasses so unit tests need no Agent mock.
VoiceAgentAssistant calls on_user_turn() then applies TurnResult to chat_ctx.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from engine.turn_result import TurnResult

logger = logging.getLogger("speaksy-engine")


class ConversationEngine:
    """Per-call engine instance (pinned config + mutable live_config)."""

    def __init__(
        self,
        live_config: dict[str, Any],
        *,
        agent_tools: Any = None,
        pinned: dict[str, Any] | None = None,
    ) -> None:
        self.live_config = live_config
        self.agent_tools = agent_tools
        self.pinned = pinned or {}

    @property
    def turn_count(self) -> int:
        tools = self.agent_tools
        return int(getattr(tools, "turn_count", 0) or 0)

    def resolve_language(self, transcript: str) -> str:
        from language_router import apply_language_to_config, resolve_turn_language

        turn_lang = resolve_turn_language(
            transcript,
            stt_language=self.live_config.get("stt_language"),
            fallback=self.live_config.get("detected_language", "en-in"),
            lang_preset=self.live_config.get("lang_preset"),
            live_config=self.live_config,
        )
        self.live_config.update(apply_language_to_config(self.live_config, turn_lang))
        return turn_lang

    def check_identity_trap(self, transcript: str, turn_lang: str) -> str | None:
        from identity_shield import handle_identity_trap_turn, load_backstory

        backstory = load_backstory(self.live_config)
        return handle_identity_trap_turn(
            transcript,
            lang=turn_lang,
            backstory=backstory,
            preset=self.live_config.get("lang_preset"),
        )

    def response_token_budget(self, transcript: str, turn: int) -> int:
        """Map ResponseLengthPolicy word ranges → max_completion_tokens."""
        from conversational_iq import ResponseLengthPolicy

        _min_w, max_w = ResponseLengthPolicy.classify_expected_length(transcript, turn)
        # ~1.3 tokens/word for code-switch Indian English; clamp to engine bounds
        base = int(self.live_config.get("llm_max_completion_tokens") or 120)
        estimated = max(40, min(base, int(max_w * 1.6) + 16))
        # Short answers: never allow huge completions
        if max_w <= 15:
            estimated = min(estimated, 64)
        elif max_w <= 25:
            estimated = min(estimated, 100)
        return estimated

    def length_instruction(self, transcript: str, turn: int) -> str:
        from conversational_iq import ResponseLengthPolicy

        return ResponseLengthPolicy.build_length_instruction(transcript, turn)

    async def on_user_turn(
        self,
        transcript: str,
        *,
        turn: int,
        max_turns: int = 40,
        speculative_hint: str | None = None,
        run_injections: bool = True,
    ) -> TurnResult:
        """Single entry for STT-final user text → TurnResult."""
        result = TurnResult()
        t0 = time.perf_counter()

        turn_lang = self.resolve_language(transcript)
        result.tts_language = str(
            self.live_config.get("tts_language")
            or self.live_config.get("detected_language")
            or turn_lang
        )

        # Identity short-circuit — never hit LLM (plan 02-007)
        deflection = self.check_identity_trap(transcript, turn_lang)
        if deflection:
            result.skip_llm = True
            result.scripted_reply = deflection
            result.identity_trap = True
            result.inject_ms = round((time.perf_counter() - t0) * 1000, 2)
            return result

        # Response length policy (plan 02-006) — was built but not applied
        tokens = self.response_token_budget(transcript, turn)
        result.max_completion_tokens = tokens
        self.live_config["_turn_max_completion_tokens"] = tokens
        length_msg = self.length_instruction(transcript, turn)
        result.system_messages.append(length_msg.strip())

        if speculative_hint:
            result.speculative_hint = speculative_hint
            result.system_messages.append(
                "[NEXT-TURN PREP — trial, use only if relevant to what the caller just said]\n"
                + speculative_hint
            )

        # Plan 05-003: barge-in rebind
        try:
            from engine.interrupt_ack import consume_interrupt_rebind

            rebind = consume_interrupt_rebind(self.live_config)
            if rebind:
                result.system_messages.append(rebind)
        except Exception:
            pass

        # Plan 04-006: returning-caller opener (first turns)
        if turn <= 2:
            opener = self.live_config.get("_returning_opener_hint")
            if opener:
                result.system_messages.append(opener)

        tracker = self.live_config.get("_deal_tracker")
        result.deal_stage = getattr(tracker, "stage", None) if tracker else None

        if run_injections:
            from turn_context_injection import compute_turn_injections

            injection_result = await compute_turn_injections(
                transcript=transcript,
                tc=turn,
                max_t=max_turns,
                live_config=self.live_config,
                agent_tools=self.agent_tools,
            )
            # apply_turn_injection_result owns these messages — do not double-add
            result.extra["injection_result"] = injection_result

        result.inject_ms = round((time.perf_counter() - t0) * 1000, 2)
        return result
