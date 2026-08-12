"""
Voicemail / no-speech detection (plan 07-007).

Deterministic heuristics — no ML dependency. Used post-call and mid-call
when user idle exceeds threshold with zero substantive transcripts.
"""
from __future__ import annotations

import re
from typing import Any

_VM_PHRASES = re.compile(
    r"\b("
    r"leave a message|after the (tone|beep)|not available|"
    r"voicemail|voice mail|mailbox|please leave|"
    r"record your message|at the tone"
    r")\b",
    re.I,
)

_BEEPISH = re.compile(r"\[?(beep|tone)\]?", re.I)


def transcript_looks_like_voicemail(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _VM_PHRASES.search(t):
        return True
    if _BEEPISH.search(t) and len(t.split()) < 12:
        return True
    return False


def classify_call_outcome(
    *,
    user_turn_count: int,
    transcript: str = "",
    duration_seconds: float = 0.0,
    booking_status: str = "",
    live_config: dict[str, Any] | None = None,
) -> str:
    """Return call_status hint: voicemail | completed | no_answer | ..."""
    cfg = live_config or {}
    if not bool(cfg.get("voicemail_detection", True)):
        return "completed"

    if "voicemail" in str(booking_status or "").lower():
        return "voicemail"

    # No user speech after a short connect → likely VM / no pickup
    if user_turn_count <= 0:
        if duration_seconds >= 8.0:
            return "voicemail"
        if duration_seconds >= 3.0:
            return "no_answer"
        return "completed"

    # STT heard a greeting machine
    if user_turn_count <= 2 and transcript_looks_like_voicemail(transcript):
        return "voicemail"

    return "completed"


def voicemail_script(live_config: dict[str, Any] | None = None) -> str:
    cfg = live_config or {}
    custom = str(cfg.get("voicemail_message") or "").strip()
    if custom:
        return custom
    company = str((cfg.get("persona") or {}).get("company") or cfg.get("company_name") or "us")
    name = str((cfg.get("persona") or {}).get("name") or "your consultant")
    return (
        f"Hi, this is {name} from {company}. "
        "Sorry we missed you — please call us back or reply on WhatsApp when free. Thank you."
    )
