"""
LiveKit worker surface (plan 01-001).

  python agent.py start  → thin shim → engine.agent_runtime
  from engine.worker import entrypoint, prewarm
"""
from __future__ import annotations

from engine.agent_runtime import _prewarm_fnc, entrypoint

prewarm = _prewarm_fnc

__all__ = ["entrypoint", "prewarm", "_prewarm_fnc"]
