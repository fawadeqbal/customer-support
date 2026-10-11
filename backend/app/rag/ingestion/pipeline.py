"""
The ingestion pipeline: documents -> chunks -> vectors -> vector store.

    data/*.pdf
      1. READ     loaders.py   text per page, tables, OCR
      2. CLEAN    cleaning.py  drop repeating headers/footers, join wrapped lines
      3. SPLIT    chunking.py  one chunk per heading/topic
      4. EMBED    the configured embeddings provider
      5. STORE    the configured vector store (pgvector by default)

    python -m scripts.ingest            build the knowledge base
    python -m scripts.ingest --preview  only show the chunks
"""
import os

from app.core import config
from app.rag.ingestion.chunking import make_chunks
from app.rag.ingestion.loaders import READERS


def load_all_chunks():
    files = sorted(f for f in os.listdir(config.DATA_DIR) if os.path.splitext(f)[1].lower() in READERS)
    if not files:
        raise SystemExit(f"No supported documents found in {config.DATA_DIR}. Add some and run again.")
    chunks = []
    for f in files:
        file_chunks = make_chunks(os.path.join(config.DATA_DIR, f))
        print(f"[read]   {f}: {len(file_chunks)} chunks")
        chunks += file_chunks
    return chunks


def run(preview=False):
    chunks = load_all_chunks()
    sizes = [len(c["content"]) for c in chunks]
    print(f"[split]  {len(chunks)} chunks, {min(sizes)}-{max(sizes)} characters each")

    if preview:
        for c in chunks:
            print(f"\n--- p.{c['page']} | {c['title']}\n{c['content'][:300]}")
        return chunks

    from app.providers import factory

    embeddings = factory.build_embeddings()
    vectors = embeddings.embed_documents([c["content"] for c in chunks])
    if len(vectors[0]) != config.EMBEDDING_DIM:
        raise SystemExit(f"{embeddings.name} makes {len(vectors[0])} numbers per vector, but "
                         f"EMBEDDING_DIM is {config.EMBEDDING_DIM}. Set EMBEDDING_DIM={len(vectors[0])}.")
    print(f"[embed]  each chunk -> {len(vectors[0])} numbers ({embeddings.name})")

    store = factory.build_vector_store()
    count = store.replace_all(chunks, vectors)
    print(f"[store]  {count} chunks saved ({store.name})")
    print("\nDone. Now start the API:  python -m app.main   (or  python -m scripts.chat)")
    return chunks
