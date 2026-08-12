# Latency best-fit settings (production-proven)

**Source:** fully optimised path documented on GCP `/opt/clients/hme` (k.md) + Operation Sub-Second settings in this repo.  
**Applied to:** `tinglish-vk-realty` as of 2026-07-10.  
**Runtime host:** `engine/agent_runtime.py` (shim: `agent.py`).

These are the **known-good** low-latency defaults — not experimental SOTA caps.

---

## Hot path (what runs on every turn)

```text
STT final (Soniox)
  → on_user_turn_completed
    → ConversationEngine / compute_turn_injections (parallel if enabled)
  → llm_node (Gemini stream)
    → first token → record_response_time / llm_ttft
    → tiered guard + circuit breaker sla_ms = 3000
    → filler guard only if filler_phrases_enabled (OFF in best-fit)
  → tts_node (stream)
    → clause drain (aggressive → 12 graphemes; else 16)
    → first PCM → record_tts_latency → ttfa_server_ms
    → record_e2e_turn_latency(ttfa_server_ms)
```

---

## Measurement (`call_quality_scorer.py`)

| Clock | When |
|-------|------|
| TTFA start | STT final (`record_user_speech_finished`) |
| STT final | same event (`record_user_final_transcript`) |
| Turn complete | `on_user_turn_completed` |
| LLM ms | first token |
| TTS ms | first PCM |

**Row fields:** `endpointing_ms`, `stt_ms`, `llm_ms`, `buffer_ms`, `tts_ms`, `ttfa_server_ms`, `ttfa_estimated_ms`, `e2e_ms`

`ttfa_estimated_ms = ttfa_server_ms + PSTN_LATENCY_ESTIMATE_MS` (default **200**)

Engine path also writes 6-stage `turn_metrics` when collector is active.

---

## Best-fit knobs (config.json + defaults)

| Knob | Best-fit value | Role |
|------|----------------|------|
| `stt_provider` | **soniox** | STT (not Sarvam on hot path) |
| `stt_model` | `stt-rt-v5` | Soniox realtime |
| `stt_min_endpointing_delay` | **0.2** s | Floor endpointing |
| `stt_max_endpointing_delay` | **0.2** s | Ceiling (tight) |
| `stt_max_endpoint_delay_ms` | **200** | ms form for STT factory |
| `stt_adaptive_endpoint_enabled` | **true** | Adaptive delay helper |
| `tts_provider` | **cartesia** | Primary TTS |
| `cartesia_tts_model` | **sonic-3.5** | Low-latency voice |
| `first_tts_chunk_fast_path` | **true** | Speak first clause ASAP |
| `tts_aggressive_chunking_enabled` | **true** | Clause threshold **12** (else 16) |
| `llm_provider` / model | **gemini** / `gemini-2.5-flash` (or flash-lite) | Streaming LLM |
| `llm_max_completion_tokens` | **200** | Cap length |
| `llm_temperature` | **0.55–0.7** | Stable short replies |
| `system_prompt_token_budget` | **1000** | Stable prefix / cache |
| `filler_phrases_enabled` | **false** | No filler path overhead |
| `silence_guard_enabled` | **false** | Off unless dead-air interventions needed |
| `bot_min_ms` / min interrupt | **350** / **0.35s**, min_words **2** | Interrupt thresholds |
| `parallel_turn_injectors_enabled` | **true** | Faster inject |
| `speculative_reply_enabled` | **true** | Next-turn prep |
| `llm_tiered_retry_ms` | **1500** | Soft retry |
| `llm_tiered_hard_cap_ms` | **3000** | = circuit SLA |
| `llm_circuit_sla_ms` | **3000** | `protected_async_iter` SLA |
| `PSTN_LATENCY_ESTIMATE_MS` | **200** | Felt estimate only |

### Env (optional overrides)

| Env | Default / note |
|-----|----------------|
| `SONIOX_API_KEY` | required for STT |
| `SYSTEM_PROMPT_TOKEN_BUDGET` | `1000` |
| `LIVEKIT_TTS_AGGRESSIVE_CHUNKING` | unset + config aggressive → clause **12**; off → **16** |
| `PSTN_LATENCY_ESTIMATE_MS` | `200` |
| `TTS_PROVIDER` | fallback if config empty; config is **cartesia** |
| `CARTESIA_TTS_MODEL` | `sonic-3.5` |

**Note:** `.env` may list `STT_PROVIDER=sarvam`; runtime STT is **soniox** from `config.json` / `build_soniox_stt`.

---

## Code files that define this behaviour

| File | Role |
|------|------|
| `config.json` | Best-fit settings + `assistant_settings` |
| `agent.py` | Thin shim → `engine.agent_runtime` |
| `engine/agent_runtime.py` | Session, nodes, events, clamps |
| `engine/ttft_policy.py` | 1500 retry / **3000** hard cap |
| `stt_provider.py` | Soniox factory + delay clamp |
| `gemini_llm.py` | Gemini stream |
| `cartesia_tts.py` / `tts_provider.py` | TTS |
| `indic_sentence_tokenizer.py` / `tts_text_transform.py` | Speak-early |
| `call_quality_scorer.py` | TTFA rows |
| `worker_prewarm.py` / `greeting_cache.py` | Cold-start |
| `turn_context_injection.py` | Per-turn injectors |
| `circuit_breaker.py` | LLM SLA (uses hard_cap_ms) |
| `engine/metrics/turn_metrics.py` | 6-stage waterfall |

---

## AgentSession call flow (verified in code)

```text
1. Config load → merge assistant_settings → build CallConfig
2. Prewarm: Silero VAD, Soniox http_session, greeting cache
3. build_soniox_stt() + Gemini LLM + Cartesia TTS
4. Memory/prompt inject; token budget warn if > 1000
5. AgentSession.start
6. Optional ambient audio; silence_guard only if enabled (OFF)
7. Greeting (cached preferred)

Per turn:
  user_input_transcribed (is_final)
    → on_stt_final → record_user_speech_finished + record_user_final_transcript  # TTFA t0
  on_user_turn_completed
    → record_turn_processing_start()
    → language resolve, identity trap (may StopResponse)
    → compute_turn_injections (parallel if enabled)
  llm_node (stream)
    → first token → record_response_time
    → circuit breaker / tiered sla_ms = 3000
    → filler guard only if filler_phrases_enabled (OFF)
  tts_node (stream)
    → clause drain → synthesize
    → first PCM → record_tts_latency → ttfa_server_ms
    → record_e2e_turn_latency(ttfa_server_ms)
```

## Audit status (local tree)

| Step | Status |
|------|--------|
| Soniox + Cartesia + Gemini | ✅ |
| Endpointing 0.2/0.2 | ✅ |
| Token budget 1000 + warn | ✅ |
| Filler off | ✅ |
| Silence guard off | ✅ |
| Circuit/TTFT SLA 3000 | ✅ |
| Aggressive TTS clause + first-chunk fast | ✅ |
| TTFA clocks on STT final | ✅ via `on_stt_final` |
| Greeting cache path | ✅ |
| Parallel injectors / speculative | ✅ |

## Verify after deploy

```bash
# Offline gate (<30s)
python3 scripts/run_latency_pipeline_30s.py --strict

# Unit suite
python3 -m pytest tests/test_latency_pipeline_30s.py tests/test_engine_foundation.py -q

# Confirm knobs loaded
python3 -c "import json; c=json.load(open('config.json')); print({k:c[k] for k in ['stt_max_endpointing_delay','system_prompt_token_budget','filler_phrases_enabled','silence_guard_enabled','llm_tiered_hard_cap_ms','tts_aggressive_chunking_enabled']})"
```

---

## Relation to SOTA plan (001 TOP10)

| Best-fit (this doc) | SOTA stretch |
|---------------------|--------------|
| LLM SLA **3000ms** | Experimental hard cap 1800ms (not default) |
| Endpointing **0.2/0.2** | Further cut only if STT stage is top of waterfall |
| Filler **off** | Keep off unless dead-air p95 needs it |

Do **not** retune away from this table without a new live journal (`n≥50`) proving a win.
