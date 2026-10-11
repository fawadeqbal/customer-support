"""Write the answer from the retrieved passages, streaming it to the browser."""
from app.graph.events import emit
from app.graph.nodes.retrieval import _add_usage


def generate(state, deps):
    conv = state["conversation"]
    emit("meta", {
        "conversation_id": conv["id"], "title": conv["title"], "route": state["route"],
        "query": state["query"], "sources": state["results"],
        "retrieve_ms": state["retrieve_ms"], "chunks_searched": deps.knowledge.chunk_count,
    })
    parts, tools, usage = [], [], {}
    chunks = [r["text"] for r in state["results"]]
    for kind, value in deps.assistant.stream(state["question"], chunks, state["history"], state["summary"]):
        if kind == "delta" and value:
            parts.append(value)
            emit("delta", {"text": value})
        elif kind == "tool":
            tools.append(value)
            emit("tool", {"name": value})
            if value == "open_support_ticket":       # the model decided a person should take over
                emit("handoff", {"form": True})       # -> the chat panel shows the ticket form
        elif kind == "usage":
            usage = value
    return {"answer": "".join(parts).strip(), "tools": tools, "usage": _add_usage(state, usage)}
