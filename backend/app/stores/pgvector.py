"""
stores/pgvector.py - THE VECTOR STORE: PostgreSQL + pgvector

Stores the chunks with their vectors and a keyword index, and runs the hybrid search
(vector + keyword, fused with Reciprocal Rank Fusion). To use another database
(Qdrant, Pinecone, ...), write a class with the same methods and register it in
app/providers/factory.py.
"""
import numpy as np

from app.core import config
from app.db.connection import connect, connect_plain

# The knowledge base table. Owned by this store (not by app/db/migrations) because its
# vector size depends on the embedding model; it is rebuilt when that size changes.
CHUNKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    content     TEXT NOT NULL,
    source      TEXT NOT NULL,
    page        INT  NOT NULL,
    embedding   vector({dim}) NOT NULL
);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT '';
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED;
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
"""

# Both searches run in one query. RRF score = 1/(60 + rank) summed over the lists a chunk appears in.
# Keyword search uses OR between the words (plainto_tsquery would require ALL of them).
HYBRID_SQL = """
WITH q AS (
    SELECT replace(plainto_tsquery('english', %(text)s)::text, '&', '|') AS ts
),
vec AS (
    SELECT id, row_number() OVER (ORDER BY embedding <=> %(vec)s) AS rank
    FROM chunks ORDER BY embedding <=> %(vec)s LIMIT %(n)s
),
kw AS (
    SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, to_tsquery('english', q.ts)) DESC) AS rank
    FROM chunks c, q
    WHERE q.ts <> '' AND c.tsv @@ to_tsquery('english', q.ts)
    ORDER BY ts_rank_cd(c.tsv, to_tsquery('english', q.ts)) DESC LIMIT %(n)s
)
SELECT c.id, c.title, c.content, c.source, c.page,
       1 - (c.embedding <=> %(vec)s)                                    AS similarity,
       coalesce(1.0 / (60 + vec.rank), 0) + coalesce(1.0 / (60 + kw.rank), 0) AS rrf,
       kw.rank                                                          AS keyword_rank
FROM chunks c
LEFT JOIN vec ON vec.id = c.id
LEFT JOIN kw  ON kw.id  = c.id
WHERE vec.id IS NOT NULL OR kw.id IS NOT NULL
ORDER BY rrf DESC
"""


class PgVectorStore:
    name = "pgvector"

    def __init__(self, dim=config.EMBEDDING_DIM):
        self.dim = dim
        self.ensure_schema()

    def ensure_schema(self):
        """Create the chunks table for this embedding size (and the keyword index next to it)."""
        with connect_plain() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(CHUNKS_SCHEMA.format(dim=self.dim))

    def _column_type(self, conn):
        row = conn.execute(
            "SELECT format_type(atttypid, atttypmod) AS t FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
        ).fetchone()
        return row["t"] if row else None

    def dimension_ok(self):
        """False when the table was built for a different embedding size (model was changed)."""
        with connect() as conn:
            return self._column_type(conn) == f"vector({self.dim})"

    def count(self):
        with connect() as conn:
            return conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]

    def search(self, query_vector, query_text, candidates):
        vec = np.asarray(query_vector, dtype=np.float32)
        with connect() as conn:
            return conn.execute(HYBRID_SQL, {"vec": vec, "text": query_text, "n": candidates}).fetchall()

    def replace_all(self, chunks, vectors):
        with connect() as conn:
            if self._column_type(conn) != f"vector({self.dim})":
                # The embedding model changed size: rebuild the chunks table for the new size
                print(f"[store]  embedding size changed -> rebuilding chunks table as vector({self.dim})")
                conn.execute("DROP TABLE IF EXISTS chunks")
        self.ensure_schema()
        rows = [(c["title"], c["content"], c["source"], c["page"], np.asarray(v, dtype=np.float32))
                for c, v in zip(chunks, vectors)]
        with connect() as conn:
            with conn.transaction():
                conn.execute("TRUNCATE chunks RESTART IDENTITY")
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO chunks (title, content, source, page, embedding) VALUES (%s, %s, %s, %s, %s)",
                        rows,
                    )
            return conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]
