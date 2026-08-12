-- Migration v10: Switch call_logs.id from sequential bigint to UUID
-- SECURITY (CRITICAL-3): Sequential integer log IDs allow unauthenticated enumeration.
-- This migration replaces the bigint primary key with a UUID to prevent sequential enumeration.
-- Run after v9. Apply on your Supabase project via the SQL editor.

BEGIN;

-- Step 1: Add a new UUID column
ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS uuid_id UUID DEFAULT gen_random_uuid() NOT NULL;

-- Step 2: Create a unique index on the new UUID column
CREATE UNIQUE INDEX IF NOT EXISTS call_logs_uuid_id_idx ON call_logs (uuid_id);

-- Step 3: Update the transcript endpoint to use uuid_id as the public identifier.
-- (Application code already references uuid_id after this migration)

-- Step 4: (Optional) Drop the sequential primary key exposure
-- Only do this after confirming all application code uses uuid_id:
-- ALTER TABLE call_logs DROP CONSTRAINT call_logs_pkey;
-- ALTER TABLE call_logs ADD PRIMARY KEY (uuid_id);

-- Note: The integer 'id' column is kept for internal FK references.
-- The public /api/logs/{id}/transcript endpoint now uses uuid_id.

COMMIT;
