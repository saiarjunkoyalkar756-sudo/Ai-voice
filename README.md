# Speaksy AI Voice Agent Platform

Multi-tenant AI phone agent SaaS platform powering real-time voice AI for Indian businesses.

**Stack:** FastAPI + LiveKit + Gemini (LLM) + Soniox (STT) + Cartesia (TTS) + Supabase + Redis

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Docker + Docker Compose (recommended)
- Supabase project
- LiveKit Cloud project
- API keys: Gemini, Soniox, Cartesia (see .env.example)

### 2. Setup

`ash
cd speaksy-platform/
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — fill all required secrets
`

### 3. Database

Run SQL migrations in order on your Supabase project:

`
sql/supabase_schema.sql        # Base schema (run first)
sql/supabase_migration_v2.sql
sql/supabase_migration_v3.sql
sql/supabase_migration_v4_agents.sql
sql/supabase_migration_v5_deepseek_summary.sql
sql/supabase_migration_v6_orgs.sql
sql/supabase_migration_v7_whatsapp.sql
sql/supabase_migration_v8_whatsapp_chat.sql
sql/supabase_migration_v9_turn_metrics.sql
sql/supabase_migration_v10_uuid_logs.sql   # Security: UUID log IDs
`

### 4. Bootstrap

`ash
python3 scripts/bootstrap_client.py
`

### 5. Run

`ash
# Terminal 1 — Voice agent
python3 agent.py start

# Terminal 2 — Dashboard UI
uvicorn ui_server:app --host 0.0.0.0 --port 8000
`

Open http://localhost:8000 and log in with DASHBOARD_USERNAME / DASHBOARD_PASSWORD.

### Docker (recommended for production)

`ash
docker compose up -d
`

---

## Client Presets

Two pre-configured agent profiles are in configs/:

| File | Client | Agent | Language |
|---|---|---|---|
| configs/cyberhost.json | Cyberhost (sp-345122) | Sumeet — cybersecurity training | Telugu/English |
| configs/hte.json | Husle Lifestyle (sp-67223) | HTE agent | Teluglish |

Copy the desired preset to config.json before starting.

---

## Security Fixes Applied

This codebase has been hardened against all findings from the 2026-08-10 penetration test:

| Finding | Fix Applied |
|---|---|
| CRITICAL-1: Public call recordings | ecording.py now returns signed URLs only |
| CRITICAL-2: Broken tenant isolation | 	enancy.py + equire_org_scope enforced on all DB queries |
| CRITICAL-3: Sequential transcript IDs | UUID-based log IDs via v10 migration |
| CRITICAL-4: Unauthenticated live calls | Auth required on all /api/local/* endpoints |
| CRITICAL-5: Outbound call abuse | /api/call/* gated by owner/dmin role |
| HIGH-6: WhatsApp webhook unauth | HMAC-SHA256 signature verification on incoming webhook |
| HIGH-7: Unauthenticated analytics | Auth added to all stats/bookings/analytics endpoints |
| HIGH-8: Public OpenAPI spec | /docs and /openapi.json disabled in ENVIRONMENT=production |
| MEDIUM-9: Security misconfiguration | CSP headers + sanitized /health response |
| CRITICAL-10: SSRF + file read via KB compiler | Absolute paths blocked; URL allowlist via KB_ALLOWED_DOMAINS |
| HIGH-11: Process control abuse | /api/system/* gated by is_superadmin=True |
| CRITICAL-12: Secrets leaked via /config | Schema-driven masking + org-scope enforced |

---

## Architecture

`
speaksy-platform/
├── agent.py                  Entry point: LiveKit voice agent worker
├── ui_server.py              FastAPI dashboard (131 API routes)
├── auth.py                   JWT authentication + RBAC
├── tenancy.py                Multi-tenant org scoping
├── platform_routes.py        Platform multi-tenant management
├── kb_compiler/              Knowledge base ingestion + compile pipeline
├── frontend/                 Dashboard UI (HTML/CSS/JS)
├── sql/                      Supabase SQL migrations (v1–v10)
├── scripts/                  Bootstrap + preflight scripts
├── cartridge/                Compiled KB cartridge
├── configs/                  Client config presets
├── data/                     Runtime data (greeting PCM cache etc.)
├── Dockerfile                Multi-stage Python 3.11 build
├── docker-compose.yml        App + Redis + WhatsApp service
└── .env.example              Full secrets template
`

---

## Production Checklist

- [ ] DISABLE_AUTH=false
- [ ] Strong JWT_SECRET (32+ random bytes)
- [ ] Strong DASHBOARD_PASSWORD and API_SETTINGS_PASSWORD
- [ ] ENVIRONMENT=production (disables /docs, /openapi.json)
- [ ] ALLOWED_ORIGINS set to real domain only
- [ ] Supabase call-recordings bucket set to **Private**
- [ ] WHATSAPP_INTERNAL_SECRET set (HMAC webhook auth)
- [ ] KB_ALLOWED_DOMAINS set for KB compiler SSRF protection
- [ ] TLS reverse proxy (Caddy/nginx) in front of port 8000
- [ ] Firewall: only expose 80/443
- [ ] Log rotation configured
