"""
Reliable post-call metrics merge (plans 07-006, 06-001).

Builds the payload fields that should land on call_logs including turn_metrics.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("speaksy-engine")


def build_call_log_metrics_patch(
    live_config: dict[str, Any] | None,
    *,
    quality_payload: dict[str, Any] | None = None,
    latency_export: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return columns suitable for call_logs update/insert."""
    cfg = live_config or {}
    lat = latency_export or {}
    patch: dict[str, Any] = {}

    turn_metrics = lat.get("turn_metrics")
    if turn_metrics is None:
        coll = cfg.get("_turn_metrics")
        if coll is not None and hasattr(coll, "export"):
            try:
                turn_metrics = coll.export()
            except Exception as exc:
                logger.debug("[POST-CALL] turn_metrics export failed: %s", exc)

    if turn_metrics is not None:
        patch["turn_metrics"] = turn_metrics

    ch = cfg.get("_config_hash") or lat.get("config_hash")
    if ch:
        patch["config_hash"] = ch

    summary = (turn_metrics or {}).get("summary") if isinstance(turn_metrics, dict) else None
    summary = summary or lat.get("summary") or {}
    if summary.get("p50_ms") is not None:
        try:
            patch["felt_latency_p50_ms"] = int(round(float(summary["p50_ms"])))
        except (TypeError, ValueError):
            pass
    if summary.get("p95_ms") is not None:
        try:
            patch["felt_latency_p95_ms"] = int(round(float(summary["p95_ms"])))
        except (TypeError, ValueError):
            pass

    if quality_payload:
        patch.setdefault("extracted_info_patch", {})
        # caller merges into extracted_info JSON
        patch["extracted_info_patch"] = {
            "quality_scores": quality_payload,
            "latency_journal": lat,
            "trace_id": cfg.get("_trace_id"),
            "is_canary": bool(cfg.get("is_canary")),
        }

    return patch


async def persist_call_log_metrics(
    *,
    room_id: str,
    phone: str,
    patch: dict[str, Any],
) -> bool:
    """Best-effort Supabase update by room_id / latest phone row."""
    if not patch or not room_id:
        return False
    try:
        import db

        sb = await db.get_supabase()
        if not sb:
            return False
        cols = {
            k: v
            for k, v in patch.items()
            if k in ("turn_metrics", "config_hash", "felt_latency_p50_ms", "felt_latency_p95_ms")
        }
        if not cols:
            return False
        # Prefer room_id match
        try:
            sb.table("call_logs").update(cols).eq("room_id", room_id).execute()
            logger.info("[POST-CALL] turn_metrics persisted room=%s keys=%s", room_id, list(cols))
            return True
        except Exception as exc:
            logger.warning("[POST-CALL] room_id update failed: %s", exc)
            if phone:
                sb.table("call_logs").update(cols).eq("phone_number", phone).order(
                    "created_at", desc=True
                ).limit(1).execute()
                return True
    except Exception as exc:
        logger.warning("[POST-CALL] persist metrics failed: %s", exc)
    return False
