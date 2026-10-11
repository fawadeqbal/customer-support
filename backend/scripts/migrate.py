"""
Apply database migrations (app/db/migrations/*.sql). Also runs automatically on startup.

    python -m scripts.migrate
"""
from app.core.logging import setup_logging
from app.db.migrate import run_migrations

if __name__ == "__main__":
    setup_logging()
    print("migrations:", ", ".join(run_migrations()))
