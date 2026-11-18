#!/usr/bin/env python3
"""
Voicely LiveKit agent — thin entry shim (VOICELY_ENGINE_MASTER_PLAN 01-001).

All runtime logic lives in engine.agent_runtime. Keep this file under ~80 lines
so deploys, supervisord, and `python agent.py start` stay stable.
"""
from __future__ import annotations

import os

# Re-export public symbols used by tests / external imports
from engine.agent_runtime import (  # noqa: F401
    AgentTools,
    VoiceAgentAssistant,
    entrypoint,
    get_live_config,
    safe_create_task,
    _prewarm_fnc,
)

__all__ = [
    "AgentTools",
    "VoiceAgentAssistant",
    "entrypoint",
    "get_live_config",
    "safe_create_task",
    "_prewarm_fnc",
]


if __name__ == "__main__":
    from livekit.agents import WorkerOptions, cli

    worker_agent_name = os.environ.get("LIVEKIT_AGENT_NAME", "inbound-voice-tinglish")
    try:
        num_idle = max(1, min(int(os.environ.get("AGENT_NUM_IDLE_PROCESSES", "4")), 16))
    except (TypeError, ValueError):
        num_idle = 4

    # Local/dev machines often sit at CPU load ≈ 1.0 (macOS load monitors can
    # report fully busy), which makes prod load_threshold=0.7 mark the worker
    # WS_FULL so LiveKit never assigns outbound dispatches. Override when
    # VOICELY_FORCE_WORKER_AVAILABLE=1 (or always report low load under that flag).
    force_available = (os.environ.get("VOICELY_FORCE_WORKER_AVAILABLE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    worker_kwargs: dict = {
        "entrypoint_fnc": entrypoint,
        "prewarm_fnc": _prewarm_fnc,
        "agent_name": worker_agent_name,
        "num_idle_processes": num_idle,
        "initialize_process_timeout": 30.0,
    }
    if force_available:
        worker_kwargs["load_fnc"] = lambda: 0.0
        worker_kwargs["load_threshold"] = 0.99

    cli.run_app(WorkerOptions(**worker_kwargs))
