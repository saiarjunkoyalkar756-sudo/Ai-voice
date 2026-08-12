"""
Stage-based LLM tool exposure — ≤4 schemas per turn for lower TTFT.

Operation Sub-Second Phase 2.3: rarely-used tools stay off the hot path.
"""
from __future__ import annotations

import logging
from typing import Any

from sales_playbook import DealStage

logger = logging.getLogger("inbound-voice-agent")

DEFAULT_MAX_TOOLS = 4

# Exactly four tools per stage (stable cached prefix per stage).
_STAGE_TOOLS: dict[str, frozenset[str]] = {
    DealStage.AWARENESS: frozenset(
        {"end_call", "log_objection", "send_listing", "check_price_history"}
    ),
    DealStage.INTEREST: frozenset(
        {"end_call", "log_objection", "send_listing", "check_price_history"}
    ),
    DealStage.CONSIDERATION: frozenset(
        {"end_call", "log_objection", "check_availability", "schedule_viewing"}
    ),
    DealStage.INTENT: frozenset(
        {"end_call", "schedule_viewing", "save_booking_intent", "send_listing"}
    ),
    DealStage.PURCHASE: frozenset(
        {"end_call", "capture_offer_intent", "save_booking_intent", "schedule_viewing"}
    ),
    DealStage.BOOKED: frozenset(
        {"end_call", "schedule_viewing", "send_listing", "get_business_hours"}
    ),
}

_SLOW_PATH_TOOLS = frozenset({"transfer_call", "escalate_to_agent"})


def resolve_deal_stage(live_config: dict | None) -> str:
    tracker = (live_config or {}).get("_deal_tracker")
    stage = getattr(tracker, "stage", None) if tracker else None
    stage = str(stage or DealStage.AWARENESS).strip().lower()
    if stage not in _STAGE_TOOLS:
        return DealStage.AWARENESS
    return stage


def allowed_tool_names(
    deal_stage: str | None = None,
    *,
    live_config: dict | None = None,
    include_slow_path: bool = False,
) -> frozenset[str]:
    stage = (deal_stage or resolve_deal_stage(live_config)).strip().lower()
    base = _STAGE_TOOLS.get(stage, _STAGE_TOOLS[DealStage.AWARENESS])
    if include_slow_path:
        return base | _SLOW_PATH_TOOLS
    return base


def _tool_name(tool: Any) -> str | None:
    for attr in ("name", "__name__"):
        val = getattr(tool, attr, None)
        if val:
            return str(val)
    info = getattr(tool, "info", None)
    if info is not None:
        name = getattr(info, "name", None)
        if name:
            return str(name)
    return None


def filter_tools_for_stage(
    tools: list[Any] | None,
    *,
    deal_stage: str | None = None,
    live_config: dict | None = None,
    max_tools: int = DEFAULT_MAX_TOOLS,
) -> list[Any]:
    """Return ≤max_tools function tools allowed for the current deal stage."""
    if not tools:
        return []
    if not bool((live_config or {}).get("stage_tool_filter_enabled", True)):
        return list(tools)

    allowed = allowed_tool_names(deal_stage, live_config=live_config)
    filtered: list[Any] = []
    for tool in tools:
        name = _tool_name(tool)
        if name and name in allowed:
            filtered.append(tool)
        if len(filtered) >= max_tools:
            break

    if len(filtered) < len(tools):
        logger.debug(
            "[TOOL-STAGE] stage=%s exposed %d/%d tools: %s",
            deal_stage or resolve_deal_stage(live_config),
            len(filtered),
            len(tools),
            [(_tool_name(t) or "?") for t in filtered],
        )
    return filtered