"""Nodes that find the right handbook passages."""
import time

from app.core import config
from app.graph.events import emit


def _add_usage(state, extra):
    u = dict(state.get("usage") or {"input": 0, "output": 0})
    u["input"] += extra.get("input", 0)
    u["output"] += extra.get("output", 0)
    return u


def rewrite(state, deps):
    """Follow-ups and Urdu -> a standalone English search query (only when needed)."""
    emit("step", {"name": "rewrite"})
    query, usage = deps.assistant.rewrite_query(state["question"], state["history"])
    return {"query": query, "usage": _add_usage(state, usage)}


def retrieve(state, deps):
    """Hybrid search + rerank. On a retry the search is wider and looser."""
    emit("step", {"name": "retrieve", "attempt": state["attempts"]})
    started = time.perf_counter()
    wider = state["attempts"] > 0
    results = deps.knowledge.search(
        state["query"],
        min_score=config.MIN_SCORE * (0.75 if wider else 1),
        candidates=config.CANDIDATES * (2 if wider else 1),
    )
    return {"results": results,
            "retrieve_ms": state["retrieve_ms"] + round((time.perf_counter() - started) * 1000)}


def broaden(state, deps):
    """Nothing relevant found: rephrase the question, then search again (once)."""
    emit("step", {"name": "broaden"})
    query, usage = deps.assistant.rewrite_query(state["question"], state["history"], force=True)
    return {"query": query, "attempts": state["attempts"] + 1, "usage": _add_usage(state, usage)}
