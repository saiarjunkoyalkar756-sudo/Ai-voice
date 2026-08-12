"""
Compile static system prompts at load — no runtime truncation.

Operation Sub-Second Phase 2: deterministic ≤800-token prefix for Gemini cache hits.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

logger = logging.getLogger("inbound-voice-agent")

DEFAULT_PROMPT_BUDGET = 800

_SLIM_SALES_CORE = (
    "\n\n[SALES — ANSWER → VALUE → QUESTION]\n"
    "1-2 sentences max. One follow-up question per turn. "
    "Never agree with negative framing. Propose site visit after 3+ positive signals. "
    "Use either/or closes (Saturday or Sunday?). Stage-specific hints arrive in TURN CONTEXT.\n"
)

_LAYER_BUDGETS: dict[str, int] = {
    "identity": 140,
    "business": 180,
    "mastery": 120,
    "employee": 80,
    "sales": 60,
    "directives": 160,
    "overlay": 60,
}


class PromptBudgetExceeded(RuntimeError):
    """Raised when strict compile cannot fit the preset budget."""


@dataclass(frozen=True)
class CompiledPrompt:
    text: str
    token_count: int
    budget: int
    preset_id: str
    content_hash: str


def _trim_layer(text: str, max_tokens: int, lang_preset: str) -> str:
    from token_counter import count_tokens, truncate_at_boundary

    block = (text or "").strip()
    if not block:
        return ""
    if count_tokens(block, lang_preset) <= max_tokens:
        return block
    return truncate_at_boundary(block, max_tokens, lang_preset)


def _ist_time_context() -> str:
    from datetime import datetime, timedelta

    import pytz

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    today_str = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%I:%M %p")
    days_lines = []
    for i in range(7):
        day = now + timedelta(days=i)
        label = "Today" if i == 0 else ("Tomorrow" if i == 1 else day.strftime("%A"))
        days_lines.append(f"  {label}: {day.strftime('%A %d %B %Y')} → ISO {day.strftime('%Y-%m-%d')}")
    days_block = "\n".join(days_lines)
    return (
        f"\n\n[SYSTEM CONTEXT]\n"
        f"Current date & time: {today_str} at {time_str} IST\n"
        f"Resolve ALL relative day references using this table:\n{days_block}\n"
        "Always use ISO dates when calling save_booking_intent. Appointments in IST (+05:30).\n"
        "Appointment booking window: 9:00 AM to 8:00 PM IST only.\n"
        "Property SITE VISITS: use schedule_viewing (WhatsApp confirmation + maps + brochure).\n"
    )


def _language_instruction(lang_preset: str) -> str:
    from language_router import get_language_directive, resolve_lang_preset

    preset_key = resolve_lang_preset(lang_preset)
    directive = get_language_directive(preset_key)
    return f"\n\n[LANGUAGE DIRECTIVE]\n{directive}"


def _build_layers(
    *,
    live_config: dict[str, Any],
    lang_preset: str,
    backstory: dict | None,
) -> list[tuple[str, str]]:
    from conversational_iq import (
        build_anti_ai_response_patterns,
        build_conversational_mastery_prompt,
    )
    from identity_shield import build_identity_anchor, build_identity_trap_handler_instruction
    from interrupt_handler import get_interrupt_instruction
    from language_router import default_language_for_config, get_language_overlay, resolve_lang_preset

    lang_preset_key = resolve_lang_preset(live_config.get("lang_preset"), live_config)
    base_instructions = str(live_config.get("agent_instructions") or "").strip()

    identity = (
        build_identity_anchor(backstory, preset=lang_preset_key)
        + build_identity_trap_handler_instruction()
        + build_anti_ai_response_patterns()
    )
    mastery = build_conversational_mastery_prompt(lang_preset_key)
    employee = _slim_employee_block(backstory, lang_preset_key, live_config)

    tts_provider = str(live_config.get("tts_provider") or "cartesia")
    tts_language = str(live_config.get("tts_language") or "en-IN")
    tts_safety = ""
    if tts_provider == "sarvam":
        tts_safety = (
            "\n[TTS] Include native script when speaking Indic; English-only lines need no prefix."
        )

    detected_lang = live_config.get("detected_language") or default_language_for_config(live_config)
    lang_overlay = get_language_overlay(detected_lang) if detected_lang else ""
    overlay = f"\n[LANGUAGE OVERLAY]\n{lang_overlay}" if lang_overlay else ""

    directives = (
        _language_instruction(lang_preset)
        + "\n\n[TOOL SAFETY] Call tools only with valid args; ask a short follow-up if required fields are missing."
        + tts_safety
        + f"\n\n{get_interrupt_instruction(lang_preset, live_config)}"
        + _ist_time_context()
    )

    return [
        ("identity", identity),
        ("business", base_instructions),
        ("mastery", mastery),
        ("employee", employee),
        ("sales", _SLIM_SALES_CORE),
        ("directives", directives),
        ("overlay", overlay),
    ]


def _slim_employee_block(
    backstory: dict | None,
    lang_preset: str,
    live_config: dict[str, Any],
) -> str:
    """Static employee persona — hot facts stay in per-turn knowledge injection."""
    bs = backstory or {}
    company = bs.get("company", "VK Realty")
    manager = bs.get("manager", "Vikram Khanna")
    experience = bs.get("experience_years", 4)
    from knowledge_pack import resolve_preset_pack

    pack = resolve_preset_pack(lang_preset or live_config.get("lang_preset"))
    office = bs.get("office_location", "Gachibowli")
    if isinstance(office, dict):
        office = office.get(pack) or next(iter(office.values()), "")
    return (
        f"\n\n[YOU WORK AT {company}]\n"
        f"Manager: {manager}. Office: {office}. {experience} years on the team.\n"
        "Answer company questions from TURN CONTEXT facts only — never invent RERA or prices.\n"
    )


def compile_system_prompt(
    live_config: dict[str, Any],
    *,
    lang_preset: str,
    backstory: dict | None = None,
    budget: int | None = None,
    strict: bool = False,
) -> CompiledPrompt:
    """
    Build the static system prompt artifact. Per-turn knowledge/stage/emotion
    must be injected via TURN CONTEXT on the user message (stable_prefix_cache).
    """
    from language_router import resolve_lang_preset
    from token_counter import count_tokens

    preset_id = resolve_lang_preset(lang_preset, live_config)
    prompt_budget = int(
        budget
        or live_config.get("system_prompt_token_budget")
        or DEFAULT_PROMPT_BUDGET
    )

    parts: list[str] = []
    for layer_name, raw in _build_layers(
        live_config=live_config,
        lang_preset=lang_preset,
        backstory=backstory,
    ):
        cap = _LAYER_BUDGETS.get(layer_name, 120)
        trimmed = _trim_layer(raw, cap, preset_id)
        if trimmed:
            parts.append(trimmed)

    text = "\n".join(parts).strip()
    token_count = count_tokens(text, preset_id)

    if token_count > prompt_budget:
        msg = (
            f"Compiled prompt {token_count} tokens exceeds budget {prompt_budget} "
            f"(preset={preset_id})"
        )
        if strict:
            raise PromptBudgetExceeded(msg)
        logger.error("[PROMPT-COMPILE] %s — applying emergency boundary trim", msg)
        from token_counter import truncate_at_boundary

        text = truncate_at_boundary(text, prompt_budget, preset_id)
        token_count = count_tokens(text, preset_id)

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    logger.info(
        "[PROMPT-COMPILE] preset=%s tokens=%d budget=%d hash=%s strict=%s",
        preset_id,
        token_count,
        prompt_budget,
        content_hash,
        strict,
    )
    return CompiledPrompt(
        text=text,
        token_count=token_count,
        budget=prompt_budget,
        preset_id=preset_id,
        content_hash=content_hash,
    )


@lru_cache(maxsize=16)
def _cached_compile(
    preset_id: str,
    budget: int,
    instructions_hash: str,
    strict: bool,
) -> CompiledPrompt | None:
    return None


def get_or_compile_system_prompt(
    live_config: dict[str, Any],
    *,
    lang_preset: str,
    backstory: dict | None = None,
    strict: bool = False,
) -> CompiledPrompt:
    """Return cached compile from live_config or compile fresh."""
    cached = live_config.get("_compiled_system_prompt")
    if isinstance(cached, CompiledPrompt):
        return cached

    compiled = compile_system_prompt(
        live_config,
        lang_preset=lang_preset,
        backstory=backstory,
        strict=strict,
    )
    live_config["_compiled_system_prompt"] = compiled
    return compiled