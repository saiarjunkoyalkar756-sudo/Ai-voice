# Speaker age & gender profiling

Sidecar on the foundational voice agent. **Does not replace Soniox STT.**

| Attribute | Source | Mode |
|-----------|--------|------|
| **Age** | Inworld STT Voice Profiles | Real-time WebSocket |
| **Gender** | Smallest AI Pulse | Pre-recorded (first ~6 s speech) |
| Emotion / pitch / accent | Inworld | Real-time (bonus) |

Soniox remains the production transcription path. A `stt_node` tee feeds a copy of caller PCM into the profiler with **zero added STT latency**.

## Enable

1. Set secrets (dashboard API keys or `.env`):
   - `INWORLD_API_KEY` — Base64 key from Inworld portal
   - `SMALLEST_API_KEY` — Smallest Pulse bearer key
2. In `config.json`:

```json
"speaker_profiling": {
  "enabled": true,
  "window_s": 6.0,
  "deadline_s": 7.0,
  "age_conf_min": 0.6,
  "inject_into_llm": true,
  "store_in_analytics": true,
  "emotion_detection": true
}
```

3. Restart agent. Watch logs for `[SPEAKER]`.

Default is **`enabled: false`**.

## Runtime

- Module: `speaker_profiler.py`
- Tee: `VoiceAgentAssistant.stt_node` in `engine/agent_runtime.py`
- Start: after session services (backchannel)
- LLM: one transient system annotation (do not verbalize demographics)
- Shutdown: closes Inworld WS + frees buffers; profile on `live_config["_speaker_profile_final"]`

## Ethics

- Probabilistic only — use for tone/pacing, not eligibility or pricing
- Prompt forbids stating age/gender to the caller
- Confirm consent language before production enablement

## Tests

```bash
python3 -m pytest tests/test_speaker_profiler.py -q
```
