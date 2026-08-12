"""
Post-critic repair — fix ALL blocking critic findings in 1–2 LLM passes.

The critic only reports; without this stage the same persona/KB mismatches
(e.g. company Cyberfrost vs THECYBERHOST) reappear on every recompile.
Repair rewrites the spoken artifacts against sources + findings so the next
critic pass is clean without a full re-synthesize.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any

from kb_compiler.llm import SYNTH_MODEL, generate_json

logger = logging.getLogger("kb-compiler")

MAX_REPAIR_ROUNDS = 2

# Names that look like brands/companies in uppercase-ish tokens
_COMPANYISH = re.compile(
    r"\b([A-Z][A-Za-z0-9]*(?:[ _-][A-Z][A-Za-z0-9]*){0,4})\b"
)


def _corpus_text(chunks: list[dict], limit: int = 20000) -> str:
    return "\n\n".join(c.get("text") or "" for c in chunks)[:limit]


def _facts_company_hints(facts: list[dict]) -> list[str]:
    hints: list[str] = []
    for f in facts[:80]:
        claim = str(f.get("claim") or "")
        value = str(f.get("value") or "").strip()
        low = claim.lower()
        if any(k in low for k in ("company", "institute", "brand", "operates as", "called")):
            if value and len(value) < 80:
                hints.append(value)
            # "X is a cybersecurity training institute"
            m = re.search(r"^([A-Z][A-Za-z0-9 ._-]{1,60})\s+is\s+a\b", claim)
            if m:
                hints.append(m.group(1).strip())
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for h in hints:
        k = h.casefold()
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out


def align_manifest_to_sources(
    manifest: dict,
    chunks: list[dict],
    facts: list[dict] | None = None,
) -> dict[str, Any]:
    """If persona.company is not grounded in the KB, replace it with the
    dominant company name from facts/sources. Returns change dict (may be empty)."""
    persona = dict(manifest.get("persona") or {})
    company = str(persona.get("company") or "").strip()
    corpus = _corpus_text(chunks)
    corpus_cf = corpus.casefold()

    changes: dict[str, Any] = {}
    if not company:
        return changes

    grounded = company.casefold() in corpus_cf
    if grounded:
        return changes

    # Prefer fact-derived company names that actually appear in the corpus
    candidates = _facts_company_hints(facts or [])
    picked = ""
    for c in candidates:
        if c and c.casefold() in corpus_cf and c.casefold() != company.casefold():
            # Prefer longer, more specific names
            if len(c) > len(picked):
                picked = c

    # Fallback: look for THECYBERHOST-style tokens / companyName field patterns
    if not picked:
        for m in re.finditer(r"(?:companyName|company name|company)\s*[`:=|]\s*[`]*([A-Za-z0-9][A-Za-z0-9 ._-]{1,60})", corpus, re.I):
            cand = m.group(1).strip(" `|*")
            if cand and cand.casefold() != company.casefold() and len(cand) > len(picked):
                picked = cand

    if not picked:
        # Last resort: most frequent ALLCAPS / Title token that isn't a common word
        stop = {"REQ", "IN", "UTC", "EMAIL", "PHONE", "STATUS", "CONTACT", "INDUSTRY", "LANGUAGE"}
        counts: dict[str, int] = {}
        for m in _COMPANYISH.finditer(corpus):
            tok = m.group(1).strip()
            if tok.upper() in stop or len(tok) < 4:
                continue
            if tok.isupper() or (tok[:1].isupper() and any(c.islower() for c in tok[1:])):
                counts[tok] = counts.get(tok, 0) + 1
        if counts:
            picked = max(counts.items(), key=lambda kv: (kv[1], len(kv[0])))[0]

    if picked and picked.casefold() != company.casefold():
        persona["company"] = picked
        manifest["persona"] = persona
        changes["persona.company"] = {"from": company, "to": picked}
        logger.info("[ALIGN] persona.company %r → %r (not grounded in sources)", company, picked)
    return changes


def persist_manifest(cdir, manifest: dict) -> None:
    import yaml
    from pathlib import Path

    path = Path(cdir) / "client.yaml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


async def repair_artifacts(
    artifacts: dict,
    chunks: list[dict],
    blocking: list[dict],
    manifest: dict,
    *,
    human_notes: str = "",
) -> dict:
    """One-shot rewrite of artifacts to clear critic blockers. Returns new artifacts dict."""
    if not blocking:
        return artifacts

    persona = manifest.get("persona") or {}
    company = persona.get("company") or ""
    corpus = _corpus_text(chunks, limit=18000)
    findings = []
    for b in blocking:
        if isinstance(b, dict):
            findings.append(f"- path={b.get('path','?')}: {b.get('reason') or b}")
        else:
            findings.append(f"- {b}")

    prompt = (
        "You are the REPAIR stage of a voice-agent knowledge compiler. "
        "The critic found BLOCKING issues. Fix the generated JSON so every "
        "spoken claim is grounded in the SOURCES and matches the persona company.\n\n"
        "HARD RULES:\n"
        f"- Agent company name must be exactly: {company or '(use the company name from SOURCES)'}\n"
        "- Never invent numbers, prices, dates, registration ids, or company names not in SOURCES.\n"
        "- Keep the same JSON schema/keys. Do not drop whole sections unless empty.\n"
        "- Fix EVERY blocking finding listed. Prefer minimal edits that clear the flag.\n"
        "- Spoken style: short phone-ready lines (≤2 sentences where already short).\n"
        "- If a line mentions a wrong company, replace with the correct company from SOURCES/persona.\n\n"
        "Return the FULL repaired artifacts JSON with top-level keys:\n"
        "company_knowledge, inventory, market_competitor, persona\n"
        "(same shapes as input).\n\n"
        f"PERSONA: {json.dumps(persona, ensure_ascii=False)}\n\n"
        f"BLOCKING FINDINGS:\n" + "\n".join(findings) + "\n\n"
        + (f"HUMAN FIX NOTES (authoritative):\n{human_notes}\n\n" if human_notes.strip() else "")
        + f"SOURCES:\n{corpus}\n\n"
        f"CURRENT ARTIFACTS JSON:\n{json.dumps(artifacts, ensure_ascii=False)[:55000]}"
    )

    result = await generate_json(prompt, temperature=0.15, max_output_tokens=16384, model=SYNTH_MODEL)
    if not isinstance(result, dict):
        logger.warning("[REPAIR] model returned non-dict — keeping original artifacts")
        return artifacts

    # Merge: only replace top-level keys that look valid
    fixed = copy.deepcopy(artifacts)
    for key in ("company_knowledge", "inventory", "market_competitor", "persona"):
        if isinstance(result.get(key), dict) and result[key]:
            fixed[key] = result[key]
    # Force persona company/name from aligned manifest when present
    if company and isinstance(fixed.get("persona"), dict):
        # Light post-pass: replace wrong company token if still leaking from old persona
        # handled in string_replace_company below
        pass
    return fixed


def string_replace_company(artifacts: dict, old: str, new: str) -> dict:
    """Deterministic bulk rename of a wrong company token across spoken fields."""
    if not old or not new or old.casefold() == new.casefold():
        return artifacts
    blob = json.dumps(artifacts, ensure_ascii=False)
    # Case-preserving-ish replace of the exact old token
    pattern = re.compile(re.escape(old), re.IGNORECASE)

    def _sub(m: re.Match) -> str:
        return new

    new_blob = pattern.sub(_sub, blob)
    if new_blob == blob:
        return artifacts
    try:
        return json.loads(new_blob)
    except json.JSONDecodeError:
        return artifacts


def _wrong_names_from_blocking(blocking: list, correct_company: str) -> list[str]:
    """Extract quoted wrong names from critic reasons (e.g. 'Cyberfrost')."""
    wrongs: list[str] = []
    correct_cf = (correct_company or "").casefold()
    for b in blocking or []:
        reason = str((b or {}).get("reason") if isinstance(b, dict) else b)
        for m in re.finditer(r"'([^']{2,60})'", reason):
            tok = m.group(1).strip()
            if not tok or tok.casefold() == correct_cf:
                continue
            # Skip long sentence fragments — we only want brand-like tokens
            if len(tok) > 48 or tok.count(" ") > 3:
                continue
            wrongs.append(tok)
    # de-dupe
    seen: set[str] = set()
    out: list[str] = []
    for w in wrongs:
        k = w.casefold()
        if k not in seen:
            seen.add(k)
            out.append(w)
    return out


async def repair_until_clean(
    artifacts: dict,
    chunks: list[dict],
    manifest: dict,
    *,
    run_critic,
    validate_artifacts,
    human_notes: str = "",
    progress=None,
    max_rounds: int = MAX_REPAIR_ROUNDS,
) -> tuple[dict, dict, dict, int]:
    """Validate → critic → repair loop. Returns (artifacts, validation, critic, rounds_used)."""
    validation = validate_artifacts(artifacts, chunks)
    critic = await run_critic(artifacts, chunks, manifest)
    rounds = 0
    persona = (manifest.get("persona") or {})
    company = str(persona.get("company") or "")

    for i in range(max_rounds):
        blocking = list(critic.get("blocking") or [])
        # Auto-repair exists to clear CRITIC blockers (persona/company mismatch).
        # A grounding/schema validation failure is the deterministic trust gate —
        # an ungrounded number must stay BLOCKED for human review, never be
        # silently rewritten by the LLM repair pass. So drive the loop off the
        # critic's blocking findings only, not validation.ok.
        if not blocking:
            break

        rounds = i + 1
        if progress:
            progress(
                f"auto-repair round {rounds}/{max_rounds} — "
                f"clearing {len(blocking)} critic blocker(s)"
            )
        logger.info("[REPAIR] round %d — %d blocking", rounds, len(blocking))

        # 1) Deterministic company renames from critic quotes (fast, high hit-rate)
        if company:
            for wrong in _wrong_names_from_blocking(blocking, company):
                artifacts = string_replace_company(artifacts, wrong, company)
            if isinstance(artifacts.get("persona"), dict):
                artifacts["persona"]["company"] = company

        # 2) LLM rewrite for remaining structural issues
        artifacts = await repair_artifacts(
            artifacts,
            chunks,
            blocking or [{"path": "*", "reason": "validation/schema issues"}],
            manifest,
            human_notes=human_notes,
        )

        # 3) Force company consistency after LLM rewrite
        if company:
            for wrong in _wrong_names_from_blocking(blocking, company):
                artifacts = string_replace_company(artifacts, wrong, company)
            if isinstance(artifacts.get("persona"), dict):
                artifacts["persona"]["company"] = company
                # first_line / instructions often re-introduce old brand — second pass
                for field in ("first_line", "agent_instructions"):
                    text = str(artifacts["persona"].get(field) or "")
                    for wrong in _wrong_names_from_blocking(blocking, company):
                        if wrong.casefold() in text.casefold():
                            artifacts["persona"][field] = re.sub(
                                re.escape(wrong), company, text, flags=re.IGNORECASE
                            )
                            text = artifacts["persona"][field]

        validation = validate_artifacts(artifacts, chunks)
        critic = await run_critic(artifacts, chunks, manifest)

    return artifacts, validation, critic, rounds
