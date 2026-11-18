"""Secret key inventories — never ship real values in client codebases.

All runtime secrets come from:
  1. Client `.env` (from `.env.example`)
  2. Dashboard Settings → API keys panel (`env_manager`)

Never embed live keys in config.json or the ship ZIP.
"""
from __future__ import annotations

from typing import Any

# Env vars clients must fill (dashboard / .env only). Keep aligned with env_manager.API_KEY_GROUPS.
SECRET_ENV_KEYS: tuple[str, ...] = (
    # LiveKit
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "LIVEKIT_AGENT_NAME",
    # LLM
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    # Speech
    "STT_PROVIDER",
    "TTS_PROVIDER",
    "SONIOX_API_KEY",
    "CARTESIA_API_KEY",
    "CARTESIA_TTS_MODEL",
    "SARVAM_API_KEY",
    "DEEPGRAM_API_KEY",
    "ELEVENLABS_API_KEY",
    "SMALLEST_API_KEY",
    "INWORLD_API_KEY",
    # Database / storage
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_S3_ACCESS_KEY",
    "SUPABASE_S3_SECRET_KEY",
    "SUPABASE_S3_ENDPOINT",
    "SUPABASE_S3_REGION",
    "SUPABASE_RECORDINGS_BUCKET",
    # Auth
    "JWT_SECRET",
    "DASHBOARD_USERNAME",
    "DASHBOARD_PASSWORD",
    "API_SETTINGS_PASSWORD",
    "DISABLE_AUTH",
    "ALLOWED_ORIGINS",
    # Telephony
    "SIP_TRUNK_ID",
    "OUTBOUND_TRUNK_ID",
    "INBOUND_PHONE_NUMBERS",
    "DEFAULT_TRANSFER_NUMBER",
    "VOBIZ_SIP_DOMAIN",
    "VOBIZ_USERNAME",
    "VOBIZ_PASSWORD",
    "VOBIZ_OUTBOUND_NUMBER",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "TWILIO_WHATSAPP_NUMBER",
    # Integrations
    "CAL_API_KEY",
    "CAL_EVENT_TYPE_ID",
    "TWENTY_API_URL",
    "TWENTY_API_KEY",
    "CRM_TYPE",
    "CRM_API_KEY",
    "CRM_BASE_URL",
    "CRM_WEBHOOK_SECRET",
    "CRM_WEBHOOK_URL",
    "REDIS_URL",
    "SENTRY_DSN",
    # Identity
    "CLIENT_ID",
    "ENVIRONMENT",
)

# Minimum set required before agent start (preflight critical)
REQUIRED_ENV_FOR_START: tuple[str, ...] = (
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "GEMINI_API_KEY",
    "SONIOX_API_KEY",
    # "CARTESIA_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "JWT_SECRET",
)

# config.json keys that must be empty / placeholder in ships
SECRET_CONFIG_KEYS: frozenset[str] = frozenset({
    "livekit_url",
    "livekit_api_key",
    "livekit_api_secret",
    "gemini_api_key",
    "openai_api_key",
    "groq_api_key",
    "cartesia_api_key",
    "sarvam_api_key",
    "soniox_api_key",
    "elevenlabs_api_key",
    "deepgram_api_key",
    "anthropic_api_key",
    "deepseek_api_key",
    "supabase_url",
    "supabase_key",
    "supabase_service_role_key",
    "jwt_secret",
    "dashboard_password",
    "dashboard_username",
    "cal_api_key",
    "sentry_dsn",
    "sip_trunk_id",
    "twilio_account_sid",
    "twilio_auth_token",
    "redis_url",
    "crm_api_key",
    "crm_webhook_secret",
    "vobiz_password",
    "api_settings_password",
})

_PLACEHOLDERS = {
    "livekit_url": "wss://YOUR_PROJECT.livekit.cloud",
    "livekit_api_key": "",
    "livekit_api_secret": "",
    "gemini_api_key": "",
    "openai_api_key": "",
    "groq_api_key": "",
    "cartesia_api_key": "",
    "sarvam_api_key": "",
    "soniox_api_key": "",
    "elevenlabs_api_key": "",
    "deepgram_api_key": "",
    "supabase_url": "https://YOUR_PROJECT.supabase.co",
    "supabase_key": "",
    "supabase_service_role_key": "",
    "jwt_secret": "",
    "dashboard_password": "",
    "dashboard_username": "admin",
    "cal_api_key": "",
    "sentry_dsn": "",
    "sip_trunk_id": "",
    "twilio_account_sid": "",
    "twilio_auth_token": "",
    "redis_url": "",
}


def sanitize_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy config with all secrets stripped for shipping."""
    import copy

    out = copy.deepcopy(raw)
    for key in list(out.keys()):
        lk = key.lower()
        if key in SECRET_CONFIG_KEYS or any(
            s in lk
            for s in (
                "api_key",
                "api_secret",
                "password",
                "jwt_secret",
                "auth_token",
                "webhook_secret",
            )
        ):
            out[key] = _PLACEHOLDERS.get(key, "")
        if lk.endswith("_url") and "livekit" in lk:
            out[key] = _PLACEHOLDERS.get("livekit_url", "")
        if lk.endswith("_url") and "supabase" in lk:
            out[key] = _PLACEHOLDERS.get("supabase_url", "")
        if isinstance(out.get(key), str) and looks_like_secret_value(out[key]):
            # belt-and-suspenders: never leave secret-shaped strings
            if any(
                s in lk
                for s in ("key", "secret", "token", "password", "dsn")
            ):
                out[key] = _PLACEHOLDERS.get(key, "")
    return out


def looks_like_secret_value(val: str) -> bool:
    v = (val or "").strip()
    if not v:
        return False
    if "YOUR_" in v or v.startswith("wss://YOUR") or "YOUR_PROJECT" in v:
        return False
    if v in ("admin", "change-me-now", "change-me-to-a-long-random-string"):
        return False
    if v.startswith(("sk_", "sk-", "AIza", "eyJ", "whsec_", "AKIA")):
        return True
    if len(v) >= 20 and any(c.isdigit() for c in v) and any(c.isalpha() for c in v):
        # heuristic — long mixed strings may be keys
        if v.lower().startswith(("http://", "https://", "wss://", "ws://")):
            return False
        return True
    return False


def scan_text_for_secrets(text: str) -> list[str]:
    """Return human-readable hits of secret-like patterns in free text."""
    import re

    hits: list[str] = []
    patterns = (
        (r"sk_car_[A-Za-z0-9]+", "cartesia_key"),
        (r"AIza[0-9A-Za-z_\-]{10,}", "google_api_key"),
        (r"sk-[a-zA-Z0-9]{20,}", "openai_style_key"),
        (r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}", "jwt_blob"),
        (r"whsec_[A-Za-z0-9]+", "webhook_secret"),
        (r"AKIA[0-9A-Z]{16}", "aws_access_key"),
    )
    for pat, label in patterns:
        if re.search(pat, text):
            hits.append(label)
    return hits
