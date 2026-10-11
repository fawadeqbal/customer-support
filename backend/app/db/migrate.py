"""
Database migrations: numbered SQL files in app/db/migrations/, applied once each, in order.
Applied files are recorded in the schema_migrations table.

    python -m scripts.migrate     (also runs automatically when the API or scripts start)

To change the schema: add a new file, e.g. 003_add_ratings.sql. Never edit an applied one.
The knowledge-base table (chunks) is owned by the vector store (app/stores/), not by migrations,
because its shape depends on the embedding model.
"""
import logging
from pathlib import Path

from app.db.connection import connect_plain

log = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations():
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with connect_plain() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                            name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
        for f in files:
            if f.name in done:
                continue
            with conn.transaction():
                conn.execute(f.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))
            log.info("applied migration %s", f.name)
    return [f.name for f in files]
