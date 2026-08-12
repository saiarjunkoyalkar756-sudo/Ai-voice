"""
Interrupt → acknowledge → re-bind to new intent (plan 05-003).

When the user barges in, inject a short ack + force the next LLM turn to
address the NEW utterance, not continue the previous monologue.
"""
from __future__ import annotations

from typing import Any

_ACK_BY_PRESET = {
    "tinglish": "Sare — cheppandi.",
    "hme": "Haan, boliye.",
    "hte": "Haan, boliye.",
    "english": "Got it — go ahead.",
}


def interrupt_ack_line(lang_preset: str | None = None) -> str:
    key = (lang_preset or "tinglish").strip().lower()
    if key in ("telugu", "telugish"):
        key = "tinglish"
    if key in ("hinglish", "hindi", "marathi"):
        key = "hme"
    return _ACK_BY_PRESET.get(key, _ACK_BY_PRESET["english"])


def build_interrupt_rebind_message(
    new_transcript: str,
    *,
    lang_preset: str | None = None,
) -> str:
    """System message after barge-in — prioritise new user intent."""
    ack = interrupt_ack_line(lang_preset)
    snippet = (new_transcript or "").strip()[:200]
    return (
        f"[INTERRUPT] User barged in. Briefly acknowledge (style: “{ack}”), "
        f"DROP the previous unfinished answer, and respond ONLY to this new utterance:\n"
        f'"{snippet}"\n'
        "One short reply + one question max."
    )


def note_interrupt(live_config: dict[str, Any], transcript: str = "") -> None:
    live_config["_last_interrupt_ts"] = __import__("time").time()
    live_config["_interrupt_pending_rebind"] = True
    live_config["_interrupt_transcript"] = (transcript or "")[:300]
    live_config["_interrupt_count"] = int(live_config.get("_interrupt_count") or 0) + 1


def consume_interrupt_rebind(live_config: dict[str, Any]) -> str | None:
    if not live_config.pop("_interrupt_pending_rebind", False):
        return None
    text = str(live_config.pop("_interrupt_transcript", "") or "")
    return build_interrupt_rebind_message(
        text, lang_preset=live_config.get("lang_preset")
    )
