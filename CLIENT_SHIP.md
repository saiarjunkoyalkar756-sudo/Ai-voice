# Client shipping (production)

## Goal

After Platform **compile → critic clean → Approve & make LIVE**, ship a full client
codebase ZIP that is:

| Included | Not included |
|----------|--------------|
| Voice engine + dashboard UI | API keys / `.env` |
| Approved persona + packs | Host secrets |
| Latency best-fit knobs | Other clients' cartridges |
| Preflight test suite | `node_modules`, `.git`, logs |
| `SHIP_README.md` + `.env.example` | Live telephony credentials |

Client only fills secrets (LiveKit, Gemini, Soniox, Cartesia, Supabase, auth,
telephony) via `.env` **or** Dashboard → Settings → API keys.

## Flow

```
Platform: upload KB → Compile → Fix/recompile until green → Approve
         → Create codebase → download ZIP
Client:   unzip → cp .env.example .env → fill keys (or dashboard)
         → python3 scripts/run_preflight.py
         → agent + ui_server
```

### Platform UI

1. Open Platform, select client
2. Review must show grounded & critic clean
3. **Approve & make LIVE**
4. **Create codebase** (builds ZIP, then downloads)
5. **Download codebase** re-downloads latest shipment

Unapproved / blocked cartridges return HTTP 409 and do not produce a ZIP.

### CLI (operators)

```bash
python3 scripts/ship_client.py <client_id>
# → clients/<client_id>/shipments/speaksy-client-….zip
```

## Preflight (mandatory)

```bash
# Fast gate (secrets + structure + ship safety + imports)
python3 scripts/run_preflight.py

# Broader offline suites (engine, golden, TTS, compiler)
python3 scripts/run_preflight.py --full

# Secrets only
python3 scripts/run_preflight.py --secrets-only
```

Exit **0** required before production start. Exit **2** = missing required secrets.

### Required secrets before start

- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `GEMINI_API_KEY`
- `SONIOX_API_KEY`
- `CARTESIA_API_KEY`
- `SUPABASE_URL`, `SUPABASE_KEY`
- `JWT_SECRET`

## What the ZIP contains (full production)

```
speaksy-client-<id>-<utc>/
  agent.py                 # thin shim → engine.agent_runtime
  engine/                  # full production runtime
  worker_prewarm.py        # greeting + knowledge + IQ prewarm
  llm_prewarm.py           # LLM context prewarm
  greeting_cache.py        # first dialogue / session PCM cache
  config.json              # full prod knobs + approved persona/first_line
  .env.example             # all secret slots, empty values
  cartridge/               # approved lock, persona, facts (audit)
  data/company_knowledge/  # approved pack
  data/greeting_pcm_cache/ # ship-time first-dialogue PCM (when platform TTS works)
  data/lang_presets.json   # language presets
  scripts/bootstrap_client.py  # prewarm + preflight (first client run)
  scripts/run_preflight.py
  tests/preflight/         # ship safety + gates
  frontend/ + ui_server.py # dashboard
  sql/                     # Supabase schema
  SHIP_README.md
  SHIP_MANIFEST.json       # inventory + checksums
  SHIP_COMPLETENESS.json   # machine checklist (first_line, prewarm, packs…)
```

### First dialogue prewarm

On **Create codebase**, Platform:

1. Bakes approved `first_line` + agent instructions into `config.json`
2. Attempts TTS prebake of first dialogue + greeting/session lines into `data/greeting_pcm_cache/`
3. Seeds from host PCM cache when available; synthesizes misses if platform TTS key/billing works
4. Writes `PREWARM_INDEX.json` when any PCM is included

If platform TTS is unavailable (e.g. Cartesia 402), ZIP still ships complete code + first_line text.
Client runs:

```bash
python3 scripts/bootstrap_client.py
```

which prewarms first dialogue with the **client's** Cartesia key before production start.

## Safety rules

1. **No secrets in git or ZIP** — `config.json` API key fields empty/placeholder
2. **Approve gate** — ship packager refuses without `compiled.lock.json` approved
3. **Dashboard owns secrets** — `env_manager` / `secrets_manager` read `.env` only
4. **Preflight before start** — production SOP for every client deploy

## After ship: client checklist

- [ ] Unzip on client host / container
- [ ] Fill `.env` or dashboard API settings
- [ ] Run Supabase SQL from `sql/`
- [ ] `python3 scripts/run_preflight.py` → exit 0
- [ ] Start: `python3 agent.py start` + `uvicorn ui_server:app --host 0.0.0.0 --port 8000`
- [ ] Smoke call + dashboard login
- [ ] Configure telephony trunks when ready
