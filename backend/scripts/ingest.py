"""
Build the knowledge base from the documents in data/.   (run from the backend folder)

    python -m scripts.ingest            read, chunk, embed and store
    python -m scripts.ingest --preview  only show the chunks

The steps live in app/rag/ingestion/.
"""
import sys

from app.core.logging import setup_logging
from app.rag.ingestion.pipeline import run

if __name__ == "__main__":
    setup_logging()
    run(preview="--preview" in sys.argv)
