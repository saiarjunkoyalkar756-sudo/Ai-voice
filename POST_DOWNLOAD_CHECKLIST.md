# Post-download checklist — run the shipped Speaksy client

Complete list only. Do in order.

## 1. Unpack & environment

- [ ] Unzip the ship ZIP on the target host
- [ ] `cd` into the unzipped folder root (where `agent.py` and `config.json` live)
- [ ] Confirm Python 3.11+ is installed (`python3 --version`)
- [ ] Create a virtualenv (recommended): `python3 -m venv .venv && source .venv/bin/activate`
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Copy env template: `cp .env.example .env`
- [ ] Never commit `.env` or put real keys in `config.json`

## 2. Required secrets (must fill before start)

- [ ] `LIVEKIT_URL` — LiveKit project WebSocket URL
- [ ] `LIVEKIT_API_KEY`
- [ ] `LIVEKIT_API_SECRET`
- [ ] `LIVEKIT_AGENT_NAME` — agent dispatch name (match LiveKit cloud / dispatch rule)
- [ ] `GEMINI_API_KEY` — LLM
- [ ] `SONIOX_API_KEY` — STT (production path)
- [ ] `CARTESIA_API_KEY` — TTS (production path)
- [ ] `CARTESIA_TTS_MODEL=sonic-3.5` (default in template)
- [ ] `STT_PROVIDER=soniox`
- [ ] `TTS_PROVIDER=cartesia`
- [ ] `SUPABASE_URL`
- [ ] `SUPABASE_KEY` (anon key)
- [ ] `JWT_SECRET` — long random string (not `change-me`)
- [ ] `DASHBOARD_USERNAME`
- [ ] `DASHBOARD_PASSWORD` — strong password
- [ ] `DISABLE_AUTH=false` in production
- [ ] `ENVIRONMENT=production`
- [ ] `CLIENT_ID` — your client id
- [ ] `ALLOWED_ORIGINS` — dashboard origin(s), comma-separated

## 3. Recommended secrets (production reliability)

- [ ] `SUPABASE_SERVICE_ROLE_KEY` — server-side DB writes
- [ ] `SUPABASE_S3_ACCESS_KEY` — call recordings (if using S3/Supabase storage)
- [ ] `SUPABASE_S3_SECRET_KEY`
- [ ] `SUPABASE_S3_ENDPOINT`
- [ ] `SUPABASE_S3_REGION`
- [ ] `SUPABASE_RECORDINGS_BUCKET=call-recordings`
- [ ] `API_SETTINGS_PASSWORD` — lock the dashboard API-keys panel

## 4. Optional secrets (when you enable the feature)

- [ ] Speaker age/gender sidecar: `SMALLEST_API_KEY` (Pulse gender), `INWORLD_API_KEY` (age / voice profile)
- [ ] After keys set: in `config.json` set `speaker_profiling.enabled` to `true` (see `SPEAKER_PROFILING.md`)
- [ ] Telephony / SIP: `SIP_TRUNK_ID`, `OUTBOUND_TRUNK_ID`, `INBOUND_PHONE_NUMBERS`, `DEFAULT_TRANSFER_NUMBER`
- [ ] Vobiz (if used): `VOBIZ_SIP_DOMAIN`, `VOBIZ_USERNAME`, `VOBIZ_PASSWORD`, `VOBIZ_OUTBOUND_NUMBER`
- [ ] Twilio: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `TWILIO_WHATSAPP_NUMBER`
- [ ] Calendar: `CAL_API_KEY`, `CAL_EVENT_TYPE_ID`
- [ ] CRM: `CRM_TYPE`, `CRM_API_KEY`, `CRM_BASE_URL`, `CRM_WEBHOOK_URL`, `CRM_WEBHOOK_SECRET`
- [ ] Twenty CRM: `TWENTY_API_URL`, `TWENTY_API_KEY`
- [ ] Observability: `SENTRY_DSN`, `REDIS_URL`
- [ ] Alternate LLM/STT/TTS keys only if you change providers: `OPENAI_API_KEY`, `GROQ_API_KEY`, `SARVAM_API_KEY`, `DEEPGRAM_API_KEY`, etc.

## 5. Supabase / database

- [ ] Create a dedicated Supabase project for this client (recommended isolation)
- [ ] Run base schema: `sql/supabase_schema.sql` (or `sql/supabase_setup.sql` per `sql/README.md`)
- [ ] Apply migrations in order: `v2` → `v3` → `v4_agents` → `v5_deepseek_summary` → `v6_orgs` → `v7_whatsapp` → `v8_whatsapp_chat` → `v9_turn_metrics`
- [ ] Apply extras if needed: `supabase_migration_lead_actions.sql`, `supabase_fix_rls.sql`
- [ ] Create recordings bucket if using call recording storage
- [ ] Confirm URL + anon + service-role keys match the project you just set up

## 6. LiveKit project

- [ ] Create / select LiveKit Cloud (or self-hosted) project
- [ ] Copy URL + API key + secret into `.env`
- [ ] Create agent dispatch rule for `LIVEKIT_AGENT_NAME`
- [ ] Confirm network access from this host to LiveKit
- [ ] (Later) Attach SIP trunk / inbound numbers when telephony goes live

## 7. Verify packaged agent config (already baked — do not wipe)

- [ ] Open `config.json` — confirm `first_line` is present (approved first dialogue)
- [ ] Confirm `agent_instructions` is present
- [ ] Confirm `stt_provider=soniox`, endpointing `0.2` / `0.2`, `filler_phrases_enabled=false`
- [ ] Confirm `tts_provider=cartesia`, `cartesia_tts_model=sonic-3.5`
- [ ] Confirm `llm_context_prewarm=true`, `system_prompt_token_budget=1000`
- [ ] Confirm API key fields in `config.json` are empty / placeholders (secrets stay in `.env`)
- [ ] Confirm `data/company_knowledge/` has the approved pack JSON
- [ ] Skim `cartridge/persona.json` and `SHIP_COMPLETENESS.json` for ship health
- [ ] Skim `SHIP_README.md` once

## 8. Bootstrap (first run — mandatory)

- [ ] `python3 scripts/bootstrap_client.py`
  - fills / checks required secrets
  - prewarms first dialogue + greeting/session PCM (`data/greeting_pcm_cache/`)
  - preloads knowledge packs + IQ registry
  - runs preflight
- [ ] Or split:
  - [ ] `python3 scripts/bootstrap_client.py --prewarm-only`
  - [ ] `python3 scripts/run_preflight.py`
- [ ] Confirm preflight exit code **0**
- [ ] Confirm `data/greeting_pcm_cache/` has `.pcm` files after prewarm (first call should not be cold)
- [ ] Optional deeper gate: `python3 scripts/run_preflight.py --full`

## 9. Start services

- [ ] Start agent worker: `python3 agent.py start`
- [ ] Start dashboard UI: `uvicorn ui_server:app --host 0.0.0.0 --port 8000`
- [ ] Or use Docker: `docker compose up -d` (if using compose) / supervisord per deploy notes
- [ ] Open dashboard: `http://<host>:8000/`
- [ ] Log in with `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD`
- [ ] Open **Settings → API keys** and confirm keys show as set (or paste any missing ones there)
- [ ] Confirm agent appears connected / idle in dashboard or LiveKit

## 10. Smoke test (before real traffic)

- [ ] Place a test browser/web call from dashboard (or LiveKit test room)
- [ ] Confirm first line plays immediately (prewarmed PCM)
- [ ] Confirm STT hears you (Soniox)
- [ ] Confirm LLM answers (Gemini)
- [ ] Confirm TTS speaks (Cartesia)
- [ ] Confirm call appears in call logs / Supabase
- [ ] Confirm recording lands if S3/bucket configured
- [ ] Fix any preflight or runtime errors before inviting real users

## 11. Telephony (when ready — not required for first voice test)

- [ ] Provision SIP trunk / DID
- [ ] Set `SIP_TRUNK_ID`, `OUTBOUND_TRUNK_ID`, `INBOUND_PHONE_NUMBERS`
- [ ] Wire LiveKit SIP → agent dispatch
- [ ] Test inbound ring → agent answers with first line
- [ ] Test outbound if used
- [ ] Set transfer number if warm transfer is required

## 12. Hardening before client go-live

- [ ] `DISABLE_AUTH=false`
- [ ] Strong `JWT_SECRET` and dashboard password
- [ ] Restrict `ALLOWED_ORIGINS` to real domains only
- [ ] Firewall: only expose needed ports (dashboard 8000 / TLS reverse proxy)
- [ ] TLS reverse proxy (nginx/caddy) in front of UI if public
- [ ] Process supervisor / systemd / Docker restart policies
- [ ] Log rotation for agent + UI
- [ ] Backup `.env` securely (secrets manager / sealed vault — not git)
- [ ] Document client-specific `LIVEKIT_AGENT_NAME` and phone numbers
- [ ] Re-run `python3 scripts/run_preflight.py` after any env change
- [ ] Re-run bootstrap/prewarm after voice or first_line change

## 13. Day-2 ops

- [ ] Monitor first production calls (latency, barge-in, hangups)
- [ ] Watch Cartesia / Soniox / Gemini billing & quotas
- [ ] Watch Supabase storage growth for recordings
- [ ] After config/persona change: restart agent (or hot-reload path) + re-prewarm
- [ ] Keep ship `cartridge/` for audit; do not delete unless you know you can recompile from Platform

## Quick command block

```bash
cd speaksy-client-<id>-*/
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env — fill all required secrets
# run sql/*.sql against Supabase
python3 scripts/bootstrap_client.py
python3 agent.py start
# other terminal:
uvicorn ui_server:app --host 0.0.0.0 --port 8000
```

## Done when

- [ ] Preflight exit 0  
- [ ] Agent + UI both running  
- [ ] Test call: first line + STT + LLM + TTS OK  
- [ ] Dashboard login works  
- [ ] Secrets only in `.env` / dashboard (not in `config.json`)  
- [ ] Telephony configured only if live calling is in scope  
