-- Runs only on the very first start (when the data volume is empty).
-- The tables themselves are created by the Python app (db.py), so they
-- always match the embedding size in config.py.
CREATE EXTENSION IF NOT EXISTS vector;
