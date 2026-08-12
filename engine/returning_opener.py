"""
Returning-caller openers (plan 04-006).

Builds a short system hint when lead history exists so first line / first
LLM turn references prior context.
"""
from __future__ import annotations

from typing import Any


def build_returning_opener_hint(
    *,
    caller_name: str = "",
    call_count: int = 0,
    last_interest: str = "",
    last_project: str = "",
    lang_preset: str = "tinglish",
) -> str | None:
    if call_count <= 0 and not last_interest and not last_project:
        return None
    name = (caller_name or "").strip() or "there"
    bits = []
    if call_count > 0:
        bits.append(f"returning caller (call #{call_count + 1})")
    if last_project:
        bits.append(f"previously interested in {last_project}")
    if last_interest:
        bits.append(f"last topic: {last_interest}")
    detail = "; ".join(bits)
    style = {
        "tinglish": f"Open warm in Tinglish — use their name {name} if natural.",
        "hme": f"Open warm in Hinglish — name {name} if natural.",
        "english": f"Open warm in English — use {name} if natural.",
    }.get((lang_preset or "tinglish").lower(), f"Open warmly for {name}.")
    return (
        f"[RETURNING CALLER] {detail}. {style} "
        "One sentence of recognition, then ask what they need today. Do not re-qualify from zero."
    )


def inject_returning_opener(live_config: dict[str, Any], lead_profile: Any = None) -> str | None:
    if not lead_profile:
        return None
    name = getattr(lead_profile, "name", None) or live_config.get("_caller_name") or ""
    call_count = int(getattr(lead_profile, "call_count", 0) or 0)
    last_interest = str(getattr(lead_profile, "last_interest", "") or "")
    last_project = str(getattr(lead_profile, "last_project", "") or getattr(lead_profile, "preferred_project", "") or "")
    hint = build_returning_opener_hint(
        caller_name=str(name or ""),
        call_count=call_count,
        last_interest=last_interest,
        last_project=last_project,
        lang_preset=str(live_config.get("lang_preset") or "tinglish"),
    )
    if hint:
        live_config["_returning_opener_hint"] = hint
    return hint
