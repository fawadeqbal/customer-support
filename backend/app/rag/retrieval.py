"""
app/rag/retrieval.py - THE "R" (RETRIEVAL) SIDE

For every question:
  1. EMBED     the question with the configured embeddings provider
  2. SEARCH    the vector store (pgvector: vector + keyword search, fused with RRF)
  3. FILTER    drop chunks that are neither similar enough nor a strong keyword hit
  4. RERANK    the configured reranker orders the survivors properly
Which embeddings / store / reranker are used is decided in config.py (app/providers/factory.py).
Filling the store happens in scripts/ingest.py.
"""
from app.core import config
from app.providers import factory


class KnowledgeBase:
    def __init__(self, embeddings=None, store=None, reranker=None):
        self.embeddings = embeddings or factory.build_embeddings()
        self.store = store or factory.build_vector_store()
        self.reranker = reranker or factory.build_reranker()
        if not self.store.dimension_ok():
            raise SystemExit(
                f"The stored vectors don't match EMBEDDING_DIM={config.EMBEDDING_DIM} "
                f"({self.embeddings.name}). Run  python -m scripts.ingest  to rebuild them."
            )
        self.chunk_count = self.store.count()
        if self.chunk_count == 0:
            raise SystemExit("The knowledge base is empty. Run  python -m scripts.ingest  first.")
        print(f"[knowledge] {self.chunk_count} chunks | store {self.store.name} | "
              f"embeddings {self.embeddings.name} | reranker {self.reranker.name}")

    def search(self, question, top_k=config.TOP_K, min_score=config.MIN_SCORE, candidates=config.CANDIDATES):
        """Returns [{"title", "text", "score", "source", "page"}, ...], best first.
        score = cosine similarity (0..1), shown in the UI and used for the cutoff."""
        rows = self.store.search(self.embeddings.embed_query(question), question, candidates)

        # Keep chunks that are similar enough, or are a top keyword match that is at least somewhat similar
        kept = [r for r in rows
                if r["similarity"] >= min_score
                or (r["keyword_rank"] is not None and r["keyword_rank"] <= 3 and r["similarity"] >= min_score * 0.6)]
        kept = kept[: max(top_k * 3, top_k)]

        scores = self.reranker.score(question, [r["content"] for r in kept])
        if scores is not None:
            kept = [r for _, r in sorted(zip(scores, kept), key=lambda x: -x[0])]

        return [
            {"title": r["title"], "text": r["content"], "score": round(float(r["similarity"]), 2),
             "source": r["source"], "page": r["page"]}
            for r in kept[:top_k]
        ]
