-- 004_ticket_details.sql: a ticket carries the customer's contact details, the issue and attached files.
ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS customer_name  TEXT;
ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS customer_email TEXT;
ALTER TABLE handoffs ADD COLUMN IF NOT EXISTS issue          TEXT;

CREATE TABLE IF NOT EXISTS ticket_files (
    id            BIGSERIAL PRIMARY KEY,
    handoff_id    BIGINT NOT NULL REFERENCES handoffs(id) ON DELETE CASCADE,
    filename      TEXT NOT NULL,
    content_type  TEXT NOT NULL,
    size_bytes    INT  NOT NULL,
    data          BYTEA NOT NULL,          -- small files (5 MB max), kept with the database backup
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ticket_files_handoff_idx ON ticket_files (handoff_id);
