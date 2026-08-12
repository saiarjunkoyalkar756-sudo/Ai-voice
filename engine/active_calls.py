"""
In-process active call registry (plan 07-001 / Dograh active_calls).

Supabase upsert remains in agent entrypoint; this registry is the deploy-drain
source of truth for GET /api/health/active-calls even when DB is down.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActiveCall:
    room_id: str
    phone: str = ""
    direction: str = "inbound"
    started_at: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)


class ActiveCallRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._calls: dict[str, ActiveCall] = {}

    def register(
        self,
        room_id: str,
        *,
        phone: str = "",
        direction: str = "inbound",
        **meta: Any,
    ) -> None:
        if not room_id:
            return
        with self._lock:
            self._calls[room_id] = ActiveCall(
                room_id=room_id,
                phone=phone or "",
                direction=direction or "inbound",
                meta=dict(meta),
            )

    def unregister(self, room_id: str) -> None:
        if not room_id:
            return
        with self._lock:
            self._calls.pop(room_id, None)

    def count(self) -> int:
        with self._lock:
            return len(self._calls)

    def list(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            return [
                {
                    "room_id": c.room_id,
                    "phone": c.phone,
                    "direction": c.direction,
                    "started_at": c.started_at,
                    "age_s": round(now - c.started_at, 1),
                    **c.meta,
                }
                for c in self._calls.values()
            ]

    def snapshot(self) -> dict[str, Any]:
        calls = self.list()
        return {
            "active": len(calls),
            "calls": calls,
            "drain_ready": len(calls) == 0,
        }


_REGISTRY = ActiveCallRegistry()


def get_registry() -> ActiveCallRegistry:
    return _REGISTRY
