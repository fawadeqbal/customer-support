-- 001_initial.sql: the app's tables (chats, messages, feedback, handoffs, orders).
-- Written so it also upgrades databases created by older versions of this project.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT NOT NULL DEFAULT 'New chat',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS visitor_id UUID;      -- who owns this chat
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS summarized_upto BIGINT NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS conversations_visitor_idx ON conversations (visitor_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id               BIGSERIAL PRIMARY KEY,
    conversation_id  UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content          TEXT NOT NULL,
    sources          JSONB,
    usage            JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS feedback TEXT CHECK (feedback IN ('up', 'down'));
CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages (conversation_id, id);
CREATE INDEX IF NOT EXISTS messages_created_idx ON messages (created_at);

CREATE TABLE IF NOT EXISTS handoffs (
    id               BIGSERIAL PRIMARY KEY,
    conversation_id  UUID REFERENCES conversations(id) ON DELETE SET NULL,
    visitor_id       UUID,
    status           TEXT NOT NULL DEFAULT 'open',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    order_no           TEXT PRIMARY KEY,
    status             TEXT NOT NULL,
    items              TEXT NOT NULL,
    total_pkr          INT  NOT NULL,
    payment            TEXT NOT NULL,
    city               TEXT NOT NULL,
    placed_at          TIMESTAMPTZ NOT NULL,
    expected_delivery  DATE,
    courier            TEXT,
    tracking_no        TEXT
);
