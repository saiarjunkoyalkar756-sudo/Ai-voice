# Tinglish VK Realty — setup

Isolated clone of `vk-realty-hme` for **Telugu + English (tinglish)** with Hyderabad knowledge packs.

## Differences from HME client

| Setting | HME (`vk-realty-hme`) | Tinglish (`tinglish-vk-realty`) |
|---------|----------------------|--------------------------------|
| `lang_preset` | `hme` | `tinglish` |
| Markets | Mumbai, Chandigarh | Hyderabad (Kokapet, Gachibowli, …) |
| Knowledge pack | `hte` inventory | `tinglish` inventory |
| Dashboard URL | `/vk-realty-hme` | `/tinglish-vk-realty` |
| Default port | `8001` | `8002` |
| `LIVEKIT_AGENT_NAME` | `inbound-voice-demo` | `inbound-voice-tinglish` |
| `RE_MEMORY_DIR` | `~/.hermes/re-voice-memory` | `~/.hermes/tinglish-vk-realty` |

Same features: caller history, zero-API token counter, parallel turn injectors (flag-off), CICD-1 ambient, org tenancy, latency stats.

## Quick start

```bash
cd tinglish-vk-realty
cp .env.example .env   # or use generated .env
python3 scripts/verify_setup.py
python3 -c "from agent_process import restart_agent_fresh; restart_agent_fresh()"
DISABLE_AUTH=true python3 -m uvicorn ui_server:app --host 0.0.0.0 --port 8002
```

Dashboard: http://127.0.0.1:8002/tinglish-vk-realty/dashboard

## Run both clients on one machine

1. HME on port **8001**, agent name `inbound-voice-demo`
2. Tinglish on port **8002**, agent name `inbound-voice-tinglish`
3. Register **both** agent names in LiveKit dispatch (two `agent.py start` processes or separate VMs)

Recreate clone after HME updates:

```bash
cd vk-realty-hme && python3 scripts/create_tinglish_client.py
```