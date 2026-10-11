"""Opening database connections."""
import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector

from app.core import config


def _open():
    try:
        return psycopg.connect(config.DATABASE_URL, autocommit=True, row_factory=dict_row,
                               connect_timeout=5)
    except psycopg.OperationalError as e:
        raise SystemExit(f"Can't reach Postgres at DATABASE_URL ({e}).\n"
                         "Start it from the RAG folder:  docker compose up -d") from None


def connect():
    """Rows come back as dicts, vectors as numpy arrays. Use as: with connect() as conn: ..."""
    conn = _open()
    register_vector(conn)
    return conn


def connect_plain():
    """Without the vector type (used by migrations, before the extension may exist)."""
    return _open()
