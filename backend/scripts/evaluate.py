"""
scripts/evaluate.py - HOW GOOD IS RETRIEVAL?  (run after scripts/ingest.py)

Each test question in eval/questions.json lists the handbook section(s) that answer it.
For every question we check whether retrieval brings back one of those sections.

    hit rate       questions where a correct section was retrieved          (higher = better)
    MRR            how high the first correct section ranks (1.0 = always first)
    no-answer      out-of-scope questions ("who is the CEO?") that correctly got NOTHING
    avg chunks     how many chunks go to Claude on average (fewer = cheaper)

    python -m scripts.evaluate              test the current settings in app/core/config.py
    python -m scripts.evaluate --sweep      try several MIN_SCORE / TOP_K values and compare
    python -m scripts.evaluate --rewrite    also use Claude query rewriting (needs the API key, costs a little)
    python -m scripts.evaluate --show       print each question's results
"""
import json
import sys

from app.core import config
from app.rag.retrieval import KnowledgeBase

QUESTIONS = json.load(open(config.EVAL_FILE, encoding="utf-8"))


def evaluate(kb, top_k, min_score, rewrite=None, show=False):
    hits = rr = 0.0
    answerable = [q for q in QUESTIONS if not q.get("out_of_scope")]
    out_of_scope = [q for q in QUESTIONS if q.get("out_of_scope")]
    no_answer_ok = 0
    total_chunks = 0
    for item in QUESTIONS:
        query = rewrite(item["q"]) if rewrite else item["q"]
        results = kb.search(query, top_k=top_k, min_score=min_score)
        titles = [r["title"].replace(" (continued)", "") for r in results]
        total_chunks += len(results)
        if item.get("out_of_scope"):
            ok = len(results) == 0
            no_answer_ok += ok
        else:
            ranks = [i for i, t in enumerate(titles) if t in item["expect"]]
            ok = bool(ranks)
            if ranks:
                hits += 1
                rr += 1 / (ranks[0] + 1)
        if show:
            print(f"{'OK ' if ok else 'MISS'} {item['q'][:55]:<55} -> {', '.join(titles) or '(nothing)'}")
    return {
        "hit_rate": hits / len(answerable),
        "mrr": rr / len(answerable),
        "no_answer": no_answer_ok / len(out_of_scope) if out_of_scope else 1.0,
        "avg_chunks": total_chunks / len(QUESTIONS),
    }


def row(label, m):
    return (f"{label:<22} hit rate {m['hit_rate']:6.1%}   MRR {m['mrr']:.2f}   "
            f"no-answer {m['no_answer']:6.1%}   avg chunks {m['avg_chunks']:.1f}")


def main():
    kb = KnowledgeBase()
    rewrite = None
    if "--rewrite" in sys.argv:
        from app.rag.generation import Assistant
        bot = Assistant()
        rewrite = lambda q: bot.rewrite_query(q, [])[0]

    print(f"\n{len(QUESTIONS)} test questions | embeddings {kb.embeddings.name} | "
          f"reranker {kb.reranker.name} | rewrite {'on' if rewrite else 'off'}\n")

    if "--sweep" in sys.argv:
        for min_score in (0.2, 0.25, 0.3, 0.35, 0.4):
            for top_k in (3, 4, 6):
                print(row(f"MIN_SCORE={min_score} TOP_K={top_k}", evaluate(kb, top_k, min_score, rewrite)))
        print("\nPick the row with a high hit rate AND a high no-answer rate, then set it in app/core/config.py (or .env).")
    else:
        m = evaluate(kb, config.TOP_K, config.MIN_SCORE, rewrite, show="--show" in sys.argv)
        print("\n" + row("current settings", m))


if __name__ == "__main__":
    main()
