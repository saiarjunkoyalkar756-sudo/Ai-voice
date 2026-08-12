# Speaksy Client Platform — Full Context (Foundational Template)

**Repo path:** `tinglish-vk-realty` (within `speaksy-clients`)  
**Role:** Foundational production Layer-2 voice agent template + Platform KB compiler + client codebase shipper  
**Last updated:** 2026-07-10  
**Status:** Production-oriented shipping path live; speaker age/gender profiler implemented (opt-in)

This document captures the **complete engineering context** for what was built: template design, Platform → Create codebase flow, secrets model, preflight gates, latency best-fit, speaker profiling (Inworld + Smallest), and how to operate / ship to clients.

---

## 1. Product goals (what we set out to do)

1. **Template codebase** with **no API keys** and **no host agent secrets** baked in.
2. **All control from the dashboard / Platform** after ship — client only fills secrets (LiveKit, Gemini, Soniox, Cartesia, Supabase, auth, telephony, optional sidecars).
3. After Platform **compile → critic clean → Approve & make LIVE**, a **Create codebase** button builds a **full production ZIP**:
   - Engine template
   - Approved agent config (persona, first line, STT hints, packs)
   - Latency best-fit knobs
   - Prewarm path + optional ship-time greeting PCM
   - Speaker profiling module (latest)
   - Preflight + bootstrap scripts + docs
4. **As many tests as practical** before starting the agent — production shipping to clients means failures are high-cost.
5. **Speaker age + gender** in the first ~5–7s of speech via a **sidecar** (does not replace Soniox STT).

---

## 2. High-level architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PLATFORM (operator)  http://127.0.0.1:8000/platform                     │
│  Upload KB → Compile → Fix → Review → Approve → Create codebase ZIP     │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ approved cartridge
                                │ clients/<id>/packs + persona + lock
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  SHIP PACKAGER  ship/packager.py                                        │
│  Template (all engine code) + sanitized config + packs + prebake PCM    │
│  + speaker_profiler + docs + preflight  →  speaksy-client-<id>-<utc>.zip│
│  NO .env, NO live API keys                                              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ download
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CLIENT HOST                                                            │
│  .env / dashboard secrets → bootstrap → preflight → agent + ui_server   │
│  Soniox STT (hot path) + optional speaker sidecar (Inworld + Smallest)  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Runtime call path (production)

```
SIP / Web caller
    → LiveKit room
    → AgentSession (engine/agent_runtime.py)
         ├─ stt_node  ──tee──▶ speaker_profiler (optional sidecar)
         │                 └─▶ Soniox stt-rt-v5 (transcription, turn detection)
         ├─ llm_node  (Gemini) + optional [SPEAKER PROFILE] system inject
         └─ tts_node  (Cartesia sonic-3.5 best-fit)
```

**Invariant:** Soniox remains the **only** production transcription STT. Smallest and Inworld are **analysis sensors**, not the main STT.

---

## 3. Platform (KB → agent → ship)

### UI / API

| Item | Location |
|------|----------|
| Platform UI | `GET /platform` → `platform_routes.py` HTML |
| Clients API | `/api/platform/clients` |
| KB upload | `POST /api/platform/clients/{id}/kb` |
| Compile | `POST .../compile` |
| Review | `GET .../review` |
| Fix + recompile | `POST .../fix` |
| Approve LIVE | `POST .../approve` |
| **Create codebase** | `POST .../ship` |
| Download ZIP | `GET .../ship/download` |
| Knowledge ZIP | `GET .../download` |

### Ship gates (HTTP 409 if blocked)

Ship refuses unless **all** are true:

1. Client exists (`clients/<id>/client.yaml`)
2. `compiled.lock.json` present
3. `lock.approved === true`
4. `lock.validation.ok === true`
5. No `lock.critic.blocking` items
6. Persona has non-empty `first_line` and `agent_instructions`

### Approved example client

- `clients/sp-67223/` — approved, validation OK, critic clean (used for e2e ship tests)
- `clients/sp-62433/` — not approved / critic blockers (ship returns 409)

### Operator CLI (no UI)

```bash
cd tinglish-vk-realty
python3 scripts/ship_client.py sp-67223
# → clients/sp-67223/shipments/speaksy-client-sp-67223-<utc>.zip
# → LATEST.txt pointer
```

### Platform open links (local)

| What | URL |
|------|-----|
| Platform | http://127.0.0.1:8000/platform |
| Dashboard | http://127.0.0.1:8000/ |

Login uses dashboard auth token in `localStorage` (`speaksy-auth-token`). If auth is on, log in on dashboard first, then open `/platform`.

---

## 4. Ship packager (what goes in the ZIP)

### Modules

| File | Responsibility |
|------|----------------|
| `ship/packager.py` | Build full production ZIP |
| `ship/prebake.py` | Ship-time first-dialogue / greeting PCM (host TTS key, never written to ZIP) |
| `ship/secrets.py` | Secret inventories, `sanitize_config`, pattern scan |
| `ship/__init__.py` | Public exports |

### Template inclusion strategy

- **All root `*.py`** (no allowlist gaps) — includes `speaker_profiler.py`, `stt_audio.py`, etc.
- Walk roots: `engine/`, `kb_compiler/`, `re_voice_memory/`, `knowledge_system/`, `sql/`, `scripts/`, `tests/`, `frontend/`, `ship/`, `data/` (filtered), `docs_html/`, `knowledge_data/`
- Root docs: `README.md`, `LATENCY_BEST_FIT_PRODUCTION.md`, `CLIENT_SHIP.md`, `CLIENT_SETUP.md`, **`POST_DOWNLOAD_CHECKLIST.md`**, **`SPEAKER_PROFILING.md`**
- Deploy: `Dockerfile`, `docker-compose.yml`, `supervisord.conf`, `requirements.txt`, `CICD-1.ogg`

### Explicitly excluded

- `.env`, host secrets, `config.json` (rebuilt sanitized)
- `clients/` (other cartridges)
- `node_modules`, `.git`, `docs-docus`, `whatsapp-service`, `flow-builder` (optional large apps)
- Host `data/greeting_pcm_cache/*.pcm` (mixed/stale) — only **ship-time prebake** PCMs are added
- `.pyc`, `.log`, `.db`, large files > ~12MB

### Baked into `config.json` (sanitized)

1. Host config deep-copied through `sanitize_config` (all API keys / passwords emptied or placeholder)
2. **`_PRODUCTION_LATENCY`** overlay (Soniox 0.2/0.2, Cartesia sonic-3.5, TTFT 1.5s/3s, filler/silence off, speculative reply, `llm_context_prewarm`, prompt budget 1000, etc.)
3. **`speaker_profiling`** block always present, **`enabled: false`** in ships (client opts in after secrets)
4. Approved **persona**: `agent_instructions`, `first_line`, `stt_hints`
5. Manifest: `lang_preset`, LLM model/temp/tokens, voice id/provider
6. Idle / call-ending default session lines for prewarm
7. `ship_meta` (client_id, approved, pack_id, prebake stats, bootstrap command)

### Approved packs mapped into ZIP

| Cartridge source | Ship path |
|------------------|-----------|
| `packs/company_knowledge.json` | `data/company_knowledge/{pack_id}.json` (+ `knowledge_data/company_knowledge.json`) |
| `packs/inventory.json` | `data/{pack_id}_inventory.json` |
| `packs/market_competitor.json` | `data/{pack_id}_market_competitor.json` |
| `persona.json`, `compiled.lock.json`, … | `cartridge/*` (audit) |

### Ship-time prebake (first dialogue)

1. Load platform host `.env` for TTS keys (**never** put keys in ZIP)
2. Seed PCM from host `data/greeting_pcm_cache` when voice/model/text keys match
3. Call `prebake_all_greetings` for first_line + session lines + preset greetings
4. Include `data/greeting_pcm_cache/*.pcm` + `PREWARM_INDEX.json` when any audio produced
5. If Cartesia billing fails (e.g. HTTP 402), ZIP still ships; client runs `scripts/bootstrap_client.py`

### ZIP artifacts always present

```
speaksy-client-<id>-<utc>/
  agent.py                    # thin shim → engine.agent_runtime
  engine/agent_runtime.py     # full runtime + stt_node speaker tee
  speaker_profiler.py         # age/gender sidecar
  config.json                 # sanitized + approved + latency + speaker_profiling
  .env.example                # all secret slots empty
  cartridge/                  # approved lock/persona/facts
  data/company_knowledge/     # approved pack
  data/greeting_pcm_cache/    # optional ship-time PCM
  scripts/run_preflight.py
  scripts/bootstrap_client.py
  scripts/ship_client.py      # (operator; also in template)
  tests/preflight/
  tests/test_speaker_profiler.py
  frontend/ + ui_server.py
  sql/
  SHIP_README.md
  SHIP_MANIFEST.json          # inventory + sha256 prefixes
  SHIP_COMPLETENESS.json      # machine checklist
  SPEAKER_PROFILING.md
  POST_DOWNLOAD_CHECKLIST.md
  CLIENT_SHIP.md
  LATENCY_BEST_FIT_PRODUCTION.md
```

### Completeness checklist keys (`SHIP_COMPLETENESS.json`)

Includes among others: `agent_shim`, `agent_runtime`, `worker_prewarm`, `llm_prewarm`, `greeting_cache`, `bootstrap`, `preflight`, `sql`, `first_line`, `agent_instructions`, `latency_best_fit`, `knowledge_pack`, `cartridge_*`, `first_dialogue_pcm`, **`speaker_profiler`**, **`speaker_profiling_config`**, **`speaker_docs`**, **`post_download_checklist`**.

---

## 5. Secrets model (dashboard / .env only)

### Principle

- **Never** embed live keys in `config.json` or the ship ZIP.
- Runtime resolves secrets: `live_config` (non-placeholder) → env → `secrets_manager.get_secret`.
- Dashboard **Settings → API keys** uses `env_manager.API_KEY_GROUPS` → writes `.env`.

### Required before agent start (`REQUIRED_ENV_FOR_START`)

- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `GEMINI_API_KEY`
- `SONIOX_API_KEY`
- `CARTESIA_API_KEY`
- `SUPABASE_URL`, `SUPABASE_KEY`
- `JWT_SECRET`

### Speaker profiling secrets (optional)

- `SMALLEST_API_KEY` — Pulse pre-recorded gender detection
- `INWORLD_API_KEY` — Base64 Basic auth for streaming voice profiles (age, pitch, emotion, accent)

Also listed in `ship/secrets.py` `SECRET_ENV_KEYS` so ship `.env.example` includes empty slots.

### Production latency best-fit (baked into ship config)

| Knob | Value |
|------|--------|
| STT | `soniox`, min/max endpointing **0.2 / 0.2**, max delay **200 ms** |
| TTS | `cartesia`, model **sonic-3.5** |
| Filler phrases | **off** |
| Silence guard | **off** |
| System prompt budget | **1000** tokens |
| TTFT retry / hard cap | **1500 / 3000** ms |
| First TTS chunk fast path | on |
| Aggressive TTS chunking | on |
| Parallel turn injectors | on |
| Speculative reply | on |
| LLM streaming | on |
| LLM context prewarm | on |

See also: `LATENCY_BEST_FIT_PRODUCTION.md`.

---

## 6. Preflight & bootstrap (mandatory before production start)

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/run_preflight.py` | Pytest `tests/preflight/` + secret gate; `--full` for broader offline suites; `--secrets-only` |
| `scripts/bootstrap_client.py` | Secrets check → worker prewarm (first dialogue PCM + packs + IQ) → preflight |
| `scripts/ship_client.py` | Operator ship without UI |

### Preflight test areas (`tests/preflight/`)

- Ship safety / sanitize / no live keys in template config
- Packager unit + **e2e ZIP** (approved cartridge)
- Production latency knobs + TTFT policy
- Engine / critical imports
- Dashboard secrets coverage
- Runtime gates (thin `agent.py`, runtime size, SQL, Dockerfile, platform ship routes)
- Template hygiene (syntax compile, exclude lists, env generator)

### Exit codes

- `0` — safe to start
- `1` — test failures
- `2` — critical missing secrets

### Client first-run sequence

```bash
cd speaksy-client-<id>-*/
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill required secrets; apply sql/*.sql on Supabase
python3 scripts/bootstrap_client.py   # prewarm + preflight
python3 agent.py start
# other terminal:
uvicorn ui_server:app --host 0.0.0.0 --port 8000
```

Full checklist: **`POST_DOWNLOAD_CHECKLIST.md`**.

---

## 7. Speaker age & gender profiling (latest feature)

### Design driver (vendor split)

Neither vendor alone gives real-time **age + gender**:

| Attribute | Vendor | Mode | Notes |
|-----------|--------|------|-------|
| **Age** | Inworld STT Voice Profiles | Streaming WS | Labels: kid / young / adult / old / unclear |
| **Gender** | Smallest Pulse | Pre-recorded only | `gender_detection=true`; **no age** on current API |
| Pitch / emotion / accent | Inworld | Streaming | Pitch = **low-confidence gender hint** only |

### Code map

| Piece | Location |
|-------|----------|
| Controller + clients | `speaker_profiler.py` |
| PCM → WAV | `stt_audio.pcm_to_wav_bytes` |
| Audio tee | `VoiceAgentAssistant.stt_node` in `engine/agent_runtime.py` |
| Start profiler | After backchannel setup in session entry (`maybe_start_speaker_profiler`) |
| LLM inject | Start of `llm_node` via `inject_speaker_annotation` |
| Teardown | `unified_shutdown_hook` → `sp.aclose()` |
| Config | `config.json` → `speaker_profiling` |
| Secrets | `call_config`, `secrets_manager`, `env_manager` |
| Tests | `tests/test_speaker_profiler.py` (unit) |
| Docs | `SPEAKER_PROFILING.md` |

### Config block (shipped; enabled false)

```json
"speaker_profiling": {
  "enabled": false,
  "window_s": 6.0,
  "deadline_s": 7.0,
  "age_conf_min": 0.6,
  "gender_provider_prior": 0.8,
  "silence_rms_floor": 350,
  "inworld_model_id": "inworld/inworld-stt-1",
  "inworld_top_n": 3,
  "smallest_model": "pulse",
  "language": "en",
  "inject_into_llm": true,
  "store_in_analytics": true,
  "emotion_detection": true
}
```

### Timeline (target)

```
t=0     profiler start; Inworld WS opens
t≈0.5s  first non-silent PCM tee'd
t≈1–3s  Inworld age (+ pitch) provisional
t≈6s    Smallest gender POST (buffered speech)
t≤7s    deadline finalize; close sockets; free buffer
```

### Reconciliation rules

- **Age:** prefer Inworld; ignore `unclear`; require `age_conf_min`
- **Gender:** Smallest authoritative when present; else pitch hint capped ≤ 0.55, `gender_source=pitch_hint`
- **Failures:** never break the call; empty/partial profile is fine
- **LLM:** one transient system note; **must not verbalize** age/gender to caller

### Endpoints used

- Inworld: `wss://api.inworld.ai/stt/v1/transcribe:streamBidirectional`  
  Auth: `Authorization: Basic $INWORLD_API_KEY`  
  First message: `transcribeConfig` with `voiceProfileConfig.enableVoiceProfile=true`
- Smallest: `POST https://api.smallest.ai/waves/v1/stt/?model=pulse`  
  Auth: `Authorization: Bearer $SMALLEST_API_KEY`  
  Multipart WAV + `gender_detection=true` (+ optional `emotion_detection`)

### Enable on a client deploy

1. Set `SMALLEST_API_KEY` and `INWORLD_API_KEY` in `.env` or dashboard  
2. Set `speaker_profiling.enabled` to `true` in `config.json`  
3. Restart agent; log lines prefix `[SPEAKER]`

### Ethics / compliance (non-optional for prod)

- Purpose: tone/pacing + aggregate analytics only — not eligibility/pricing/routing discrimination  
- Do not persist raw buffered audio beyond the call window  
- Default **off**; per-tenant opt-in  
- Legal/consent review before enabling on real callers  

---

## 8. Engine structure (foundational template)

| Area | Notes |
|------|--------|
| `agent.py` | **Thin shim** (~lines) → `engine.agent_runtime` |
| `engine/agent_runtime.py` | Main LiveKit agent: session, STT/LLM/TTS nodes, tools, shutdown |
| `engine/conversation_engine.py` | Conversation orchestration helpers |
| `engine/ttft_policy.py` | TTFT defaults (retry 1500 / hard 3000) |
| `engine/metrics/` | Turn metrics |
| `worker_prewarm.py` | Greeting/filler/session PCM + knowledge + IQ at worker start |
| `llm_prewarm.py` | LLM context prewarm around greeting |
| `greeting_cache.py` | Disk PCM cache under `data/greeting_pcm_cache/` |
| `stt_provider.py` | Soniox LiveKit plugin builder |
| `kb_compiler/` | Platform KB compile / critic / bake / approve |

---

## 9. Related documentation index

| Doc | Purpose |
|-----|---------|
| **`FULL_CONTEXT.md`** (this file) | Complete project context |
| `CLIENT_SHIP.md` | Shipping SOP (Platform → ZIP) |
| `POST_DOWNLOAD_CHECKLIST.md` | Client checklist after unzip |
| `SPEAKER_PROFILING.md` | Age/gender feature ops |
| `LATENCY_BEST_FIT_PRODUCTION.md` | Production latency knobs |
| `SHIP_README.md` | Generated inside each client ZIP |
| `SHIP_MANIFEST.json` | Generated file inventory |
| `SHIP_COMPLETENESS.json` | Generated machine checklist |
| External plan | `/Users/nivi/Downloads/AGE_GENDER_DETECTION_IMPLEMENTATION_PLAN.md` (design source for speaker profiler) |

---

## 10. Testing status (as of last verification)

| Suite | Result |
|-------|--------|
| `tests/preflight/` | Full suite green (includes ship e2e with speaker files) |
| `tests/test_speaker_profiler.py` | 9 unit tests green |
| Ship e2e for `sp-67223` | Includes `speaker_profiler.py`, docs, config block, env keys; completeness missing `[]` |
| Platform ship API | Unapproved → 409; approved → 200 + ZIP |

Commands:

```bash
python3 -m pytest tests/preflight/ -q
python3 -m pytest tests/test_speaker_profiler.py -q
python3 scripts/ship_client.py sp-67223
python3 scripts/run_preflight.py
```

---

## 11. Known limitations / ops notes

1. **Cartesia 402** on platform host may prevent full ship-time greeting PCM; client `bootstrap_client.py` is the fallback. Host cache seed can still attach some PCMs.
2. **Speaker profiling default off** in ships — requires client keys + explicit enable.
3. **Smallest age** is not used (API does not support age prediction on current Pulse pre-recorded path per product constraints).
4. **Inworld has no gender** — only pitch hint until Smallest returns.
5. **whatsapp-service** and **flow-builder** are not packed in the default ship ZIP (size / optional).
6. Host local `.env` may hold operator keys for platform compile/prebake; those keys must never be packed into client ZIPs (packager + tests enforce).
7. UI process on port **8000** must be restarted after packager/route changes so Create codebase serves latest code.

---

## 12. Decision log (summary)

| Decision | Rationale |
|----------|-----------|
| Secrets only in `.env` / dashboard | Safe multi-client shipping; no key leakage in git/ZIP |
| Approve gate before ship | Nothing ships unsigned / unvalidated |
| Full tree ship (all root py) | Avoid missing modules (prewarm, profiler, tools) |
| Soniox hot path unchanged | Proven latency path; sidecars for demographics only |
| Dual vendor for age+gender | Capability gap: neither vendor alone is enough in real-time |
| Feature flags default off | Ethics + cost + keys not assumed |
| Preflight mandatory | Client shipping = production risk surface |
| Thin `agent.py` | Keep runtime in `engine/agent_runtime` for maintainability |

---

## 13. Quick operator playbook

### Ship a new client codebase

1. Open http://127.0.0.1:8000/platform  
2. Create/select client → upload KB → Compile  
3. Fix critic/validation issues → recompile until green  
4. **Approve & make LIVE**  
5. **Create codebase** → download ZIP (or `python3 scripts/ship_client.py <id>`)  
6. Hand ZIP + `POST_DOWNLOAD_CHECKLIST.md` to client  

### Client go-live (minimal)

1. Unzip, venv, `pip install -r requirements.txt`  
2. `.env` from `.env.example` — fill required secrets  
3. Run Supabase SQL from `sql/`  
4. `python3 scripts/bootstrap_client.py`  
5. Start agent + UI  
6. Smoke call  
7. Optional: enable speaker profiling after keys  

### Enable speaker profiling later

1. `SMALLEST_API_KEY` + `INWORLD_API_KEY`  
2. `config.json` → `speaker_profiling.enabled = true`  
3. Restart agent; confirm `[SPEAKER]` logs  

---

## 14. Key file tree (shipping-related)

```
tinglish-vk-realty/
├── agent.py
├── engine/agent_runtime.py      # stt_node tee, profiler start, llm inject, shutdown
├── speaker_profiler.py          # Inworld + Smallest + SpeakerProfile
├── stt_audio.py                 # frame_to_pcm16_mono, pcm_rms, pcm_to_wav_bytes
├── stt_provider.py              # Soniox production STT
├── worker_prewarm.py / llm_prewarm.py / greeting_cache.py
├── platform_routes.py           # Platform UI + /ship API
├── ship/
│   ├── packager.py
│   ├── prebake.py
│   └── secrets.py
├── scripts/
│   ├── ship_client.py
│   ├── run_preflight.py
│   └── bootstrap_client.py
├── tests/
│   ├── preflight/               # production ship gates
│   └── test_speaker_profiler.py
├── clients/<id>/                # cartridges (not shipped wholesale)
│   └── shipments/               # built ZIPs + LATEST.txt
├── config.json                  # host config (sanitized for ship)
├── .env.example                 # template slots (no secrets)
├── FULL_CONTEXT.md              # this document
├── CLIENT_SHIP.md
├── POST_DOWNLOAD_CHECKLIST.md
└── SPEAKER_PROFILING.md
```

---

## 15. End state (what “done” means)

- Platform can **Create codebase** after approve and produce a **full production client ZIP**.  
- ZIP has **no API keys**; client fills LiveKit / Gemini / Soniox / Cartesia / Supabase / auth / telephony via `.env` or dashboard.  
- Latency best-fit and approved persona/packs are **baked**.  
- First dialogue prewarm is **attempted at ship time** and always available via **bootstrap** on the client.  
- **Speaker age/gender** code + config + env slots + docs are **in every new ship**; feature **opt-in**.  
- **Preflight suite** must pass before production start.  

*This file is the single detailed context dump for the shipping + template + speaker-profiling workstream. Prefer updating this when the architecture changes rather than scattering tribal knowledge.*
