-- 003_support_queue.sql: live handoff to a human agent.
--   handoffs become tickets that wait in a queue, get claimed by an agent and closed.
--   messages can now also come from an agent or the system ("Ali joined the chat").

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_role_check;
ALTER TABLE messages ADD CONSTRAINT messages_role_check
    CHECK (role IN ('user', 'assistant', 'agent', 'system'));
ALTER TABLE messages ADD COLUMN IF NOT EXISTS author TEXT;          -- agent name for role 'agent'

UPDATE handoffs SET status = 'waiting' WHERE status = 'open';     -- old tickets join the queue
ALTER TABLE handoffs ALTER COLUMN status SET DEFAULT 'waiting';
ALTER TABLE handoffs DROP CONSTRAINT IF EXISTS handoffs_status_check;
ALTER TABLE handoffs ADD CONSTRAINT handoffs_status_check
    CHECK (status IN ('waiting', 'active', 'closed'));
ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS reason     TEXT;      -- what the customer asked
ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS agent      TEXT;      -- who took it
ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;
ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS closed_at  TIMESTAMPTZ;
ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS closed_by  TEXT;      -- agent name or 'customer'
CREATE INDEX IF NOT EXISTS handoffs_status_idx ON handoffs (status, id);
CREATE INDEX IF NOT EXISTS handoffs_conversation_idx ON handoffs (conversation_id);
