"""
Pipeline orchestrator — one call runs the whole compiler with progress state
the dashboard can poll (clients/<id>/compile_state.json).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("kb-compiler")

_STAGES = [
    ("ingest", 10), ("extract", 30), ("synthesize", 65),
    ("validate", 75), ("critic", 90), ("bake", 100),
]


def load_manifest(cdir: Path) -> dict:
    import yaml

    path = cdir / "client.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"client.yaml missing in {cdir}")
    manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    manifest.setdefault("client_id", cdir.name)
    manifest.setdefault("industry", "real_estate")
    manifest.setdefault("lang_preset", "tinglish")
    return manifest


def _state_path(cdir: Path) -> Path:
    return cdir / "compile_state.json"


def write_json_atomic(path: Path, obj: Any) -> None:
    """tmp + rename so a crash mid-write never leaves corrupt JSON behind."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _write_state(cdir: Path, **fields: Any) -> None:
    state = read_compile_state(cdir)
    state.update(fields)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(_state_path(cdir), state)


def read_compile_state(cdir: Path) -> dict[str, Any]:
    path = _state_path(cdir)
    if not path.is_file():
        return {"stage": "idle", "pct": 0, "running": False}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"stage": "idle", "pct": 0, "running": False}


def reconcile_state(cdir: Path, task_alive: bool) -> dict[str, Any]:
    """State says running but no live task = the process died mid-compile
    (restart/crash). Convert the orphan into a clear, recoverable error so
    the dashboard never spins forever."""
    state = read_compile_state(cdir)
    if state.get("running") and not task_alive:
        _write_state(
            cdir, running=False, stage="error",
            error="Compile was interrupted (server restarted) — run it again.",
            message="interrupted — recompile to continue",
        )
        state = read_compile_state(cdir)
    return state


def _load_human_fix_notes(cdir: Path) -> str:
    """Collect authoritative human fix notes from kb/_platform_fixes.md if present."""
    path = cdir / "kb" / "_platform_fixes.md"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-8000:]
    except OSError:
        return ""


async def run_compile(client_id: str, repo_root: Path) -> dict[str, Any]:
    """Ingest → extract → align → synthesize → validate → critic → repair×2 → bake.

    Extraction on Flash, synthesis on Pro, critic on a separate model
    (kb_compiler.llm stage contract). Auto-repair clears critic blockers in
    ≤2 passes so a single Compile/Fix click usually lands READY FOR REVIEW.
    """
    from kb_compiler.bake import bake_cartridge, client_dir
    from kb_compiler.critic import run_critic
    from kb_compiler.ingest import ingest_sources
    from kb_compiler.repair import align_manifest_to_sources, persist_manifest, repair_until_clean
    from kb_compiler.synthesize import extract_facts, synthesize_all
    from kb_compiler.validate import validate_artifacts

    cdir = client_dir(repo_root, client_id)
    t0 = time.perf_counter()
    try:
        manifest = load_manifest(cdir)
        _write_state(cdir, running=True, stage="ingest", pct=2, error=None,
                     message="reading knowledge sources")

        sources = [str(s) for s in (manifest.get("knowledge_sources") or [])]
        kb_dir = cdir / "kb"
        if kb_dir.is_dir():
            sources.extend(str(p.relative_to(cdir)) for p in sorted(kb_dir.glob("*")) if p.is_file())
        chunks = ingest_sources(sources, cdir)
        if not chunks:
            raise ValueError("No readable knowledge sources — drop files into kb/ or set knowledge_sources")
        from kb_compiler.llm import EXTRACT_MODEL, SYNTH_MODEL

        _write_state(cdir, stage="extract", pct=10,
                     message=f"{len(chunks)} chunks — extracting facts ({EXTRACT_MODEL})")

        facts = await extract_facts(chunks)
        if not facts:
            raise ValueError(
                "Fact extraction produced nothing — the KB was read "
                f"({len(chunks)} chunks) but the model returned no claims. "
                "Check VOICELY_COMPILER_EXTRACT_MODEL / GEMINI_API_KEY, or try a richer source."
            )

        # Persona/company that doesn't appear in the KB is the #1 critic loop.
        align_changes = align_manifest_to_sources(manifest, chunks, facts)
        if align_changes:
            persist_manifest(cdir, manifest)
            _write_state(cdir, message=f"aligned persona to sources: {align_changes}")

        human_notes = _load_human_fix_notes(cdir)
        _write_state(cdir, stage="synthesize", pct=30,
                     message=f"{len(facts)} grounded facts — building containers ({SYNTH_MODEL})")

        def _progress(msg: str) -> None:
            _write_state(cdir, message=msg)

        artifacts = await synthesize_all(facts, manifest, progress=_progress)
        _write_state(cdir, stage="validate", pct=65, message="running deterministic validators")

        validation = validate_artifacts(artifacts, chunks)
        _write_state(cdir, stage="critic", pct=75,
                     message=f"validation {'OK' if validation['ok'] else 'FAILED'} — critic + auto-repair")

        artifacts, validation, critic, repair_rounds = await repair_until_clean(
            artifacts, chunks, manifest,
            run_critic=run_critic,
            validate_artifacts=validate_artifacts,
            human_notes=human_notes,
            progress=_progress,
        )
        if repair_rounds:
            _write_state(cdir, message=f"auto-repair finished ({repair_rounds} round(s))")

        _write_state(cdir, stage="bake", pct=90, message="writing cartridge + lockfile")

        # Persist raw artifacts + grounding facts for the review screen
        write_json_atomic(cdir / "artifacts.json", artifacts)
        write_json_atomic(cdir / "facts.json", facts)
        lock = bake_cartridge(cdir, manifest, artifacts, validation, critic)
        if repair_rounds:
            lock["repair_rounds"] = repair_rounds
            write_json_atomic(cdir / "compiled.lock.json", lock)

        elapsed = round(time.perf_counter() - t0, 1)
        ok = validation["ok"] and not (critic.get("blocking") or [])
        if ok:
            msg = f"compiled in {elapsed}s — READY FOR REVIEW"
            if repair_rounds:
                msg += f" (auto-repaired ×{repair_rounds})"
            if align_changes:
                msg += " · persona aligned to KB"
        else:
            left = len(critic.get("blocking") or [])
            msg = (
                f"compiled in {elapsed}s — BLOCKED: {left} critic issue(s) remain after "
                f"auto-repair ×{repair_rounds}. Use Fix errors with the exact correct facts."
            )
        _write_state(
            cdir, running=False, stage="done", pct=100,
            message=msg,
            validation=validation, critic=critic, elapsed_s=elapsed,
            repair_rounds=repair_rounds, align_changes=align_changes or None,
        )
        return {
            "success": True, "validation": validation, "critic": critic, "lock": lock,
            "repair_rounds": repair_rounds, "align_changes": align_changes,
        }
    except Exception as exc:
        logger.exception("[PIPELINE] compile failed for %s", client_id)
        _write_state(cdir, running=False, stage="error", error=str(exc),
                     message=f"compile failed: {exc}")
        return {"success": False, "error": str(exc)}
