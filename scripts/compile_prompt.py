#!/usr/bin/env python3
"""CI gate: compile static system prompt per preset; fail if over token budget."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    from identity_shield import load_backstory
    from language_router import resolve_lang_preset
    from preset_contract import list_preset_ids
    from prompt_compiler import PromptBudgetExceeded, compile_system_prompt

    config_path = _ROOT / "config.json"
    live_config = json.loads(config_path.read_text(encoding="utf-8"))
    budget = int(live_config.get("system_prompt_token_budget") or 800)
    presets = list_preset_ids() or ["tinglish"]

    failed = False
    for preset in presets:
        live_config["lang_preset"] = preset
        lang = resolve_lang_preset(preset, live_config)
        backstory = load_backstory(live_config)
        try:
            compiled = compile_system_prompt(
                live_config,
                lang_preset=lang,
                backstory=backstory,
                budget=budget,
                strict=True,
            )
            print(
                f"PASS {preset}: {compiled.token_count} tokens "
                f"(budget {compiled.budget}) hash={compiled.content_hash}"
            )
        except PromptBudgetExceeded as exc:
            failed = True
            print(f"FAIL {preset}: {exc}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())