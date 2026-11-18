# Voicely Engine Package

Production conversation engine extracted per **VOICELY_ENGINE_MASTER_PLAN**.

## Layout

| Module | Plan | Role |
|--------|------|------|
| `metrics/turn_metrics.py` | 06-001, 03-001 | Per-stage turn timing |
| `pipeline_stages.py` | 01-002 | Explicit stage enum + diagram |
| `turn_result.py` | 02-002 | Engine ↔ LLM/TTS contract |
| `conversation_engine.py` | 02-001 | Sales turn orchestration |
| `active_calls.py` | 07-001 | Deploy-drain registry |
| `pinned_config.py` | 01-006 | Freeze config at call start |
| `interrupt_policy.py` | 05-001/002 | Per-phase barge-in |
| `ttft_policy.py` | 03-002 | LLM hard cap tiers |

## Host boundary

| File | Role |
|------|------|
| `agent.py` | **Thin shim** (~50 lines) — `python agent.py start` |
| `engine/agent_runtime.py` | Full LiveKit host (session, SIP, tools, nodes) |
| `engine/worker.py` | `entrypoint` / `prewarm` re-exports |
| `engine/*` | Metrics, ConversationEngine, policies |

Turn intelligence → `ConversationEngine`. Metrics → `TurnMetricsCollector`.

## Modules (v1.1)

| File | Plan |
|------|------|
| `metrics/turn_metrics.py` | 06-001, 03-001 |
| `pipeline_stages.py` | 01-002 |
| `conversation_engine.py` | 02-001 |
| `turn_result.py` | 02-002 |
| `ttft_policy.py` | 03-002 |
| `pinned_config.py` | 01-006 |
| `active_calls.py` | 07-001 |
| `interrupt_policy.py` | 05-002 |
| `interrupt_ack.py` | 05-003 |
| `tracing.py` | 06-003 |
| `voicemail.py` | 07-007 |
| `post_call_export.py` | 07-006, 06-001 |
| `canary.py` | 07-005, 02-004 |
| `stt_context_expand.py` | 08-001 |
| `returning_opener.py` | 04-006 |
| `dream_bridge.py` | 02-008 |
| `llm_node_helpers.py` | 01-001 |
| `worker.py` | 01-001 re-export |

## Success gates

- Every turn logs all 6 stages when instrumentation is active
- `GET /api/health/active-calls` returns process-local active rooms
- `pytest tests/test_engine_*.py tests/test_engine_complete.py` green without LiveKit
- Canary: `./scripts/canary_rollout.sh 10`

## Realtime S2S (08-006)

Voicely remains **STT→LLM→TTS** on the sales path so tools (booking, WhatsApp, CRM) stay first-class.  
A speech-to-speech transport can be added as a parallel session type later; it must not replace tool-capable turns.
