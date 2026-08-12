"""
Gemini API endpoint resolution — regional preference for India deploys.

API-key mode uses the global Generative Language OpenAI-compat endpoint; co-locating
the agent worker in asia-south1 (Mumbai) still cuts RTT to Google/Soniox/Cartesia edges.

Vertex mode (service account) uses regional aiplatform.googleapis.com when enabled.
"""
from __future__ import annotations

import os


DEFAULT_GEMINI_REGION = "asia-south1"
_GLOBAL_OPENAI_COMPAT = "https://generativelanguage.googleapis.com/v1beta/openai/"


def gemini_use_vertex() -> bool:
    return os.environ.get("GEMINI_USE_VERTEX", "").strip().lower() in ("1", "true", "yes", "on")


def gemini_api_region() -> str:
    return (os.environ.get("GEMINI_API_REGION") or DEFAULT_GEMINI_REGION).strip() or DEFAULT_GEMINI_REGION


def resolve_gemini_base_url() -> str:
    """
    OpenAI-compat base URL for LiveKit's openai.LLM plugin.

    Vertex + OpenAI shim is experimental; default remains global API key endpoint.
    """
    if gemini_use_vertex():
        project = (os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT") or "").strip()
        region = gemini_api_region()
        if project:
            return (
                f"https://{region}-aiplatform.googleapis.com/v1/"
                f"projects/{project}/locations/{region}/endpoints/openapi/"
            )
    return _GLOBAL_OPENAI_COMPAT


def resolve_gemini_location_label() -> str:
    if gemini_use_vertex():
        return f"vertex:{gemini_api_region()}"
    return f"global-openai-compat (worker region: {gemini_api_region()})"