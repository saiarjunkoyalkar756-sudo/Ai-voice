-- Speaksy Engine Master Plan 06-001
-- Truthful per-stage turn metrics on call_logs

ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS turn_metrics jsonb;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS config_hash text;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS felt_latency_p50_ms int;
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS felt_latency_p95_ms int;

COMMENT ON COLUMN call_logs.turn_metrics IS
  'Array/object of per-turn stage timings (speaksy.turn_metrics.v1): stt_final, turn_inject, llm_ttft, reply_buffer, tts_ttfa, first_audio_out';
COMMENT ON COLUMN call_logs.config_hash IS
  'SHA-256 prefix of pinned call definition at session start (plan 01-006)';

-- Optional index for weekly waterfall SQL
CREATE INDEX IF NOT EXISTS idx_call_logs_config_hash ON call_logs (config_hash)
  WHERE config_hash IS NOT NULL;
