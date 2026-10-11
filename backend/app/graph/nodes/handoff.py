"""'Talk to a person': ask for the ticket form (name, email, issue, files). No model call needed.
The ticket itself is opened by POST /api/handoff when the customer sends the form."""
from app.graph.events import emit
from app.prompts import load_prompt


def handoff(state, deps):
    conv = state["conversation"]
    answer = load_prompt("handoff_reply")
    emit("meta", {"conversation_id": conv["id"], "title": conv["title"], "route": "handoff",
                  "query": state["question"], "sources": [], "retrieve_ms": 0,
                  "chunks_searched": deps.knowledge.chunk_count})
    emit("handoff", {"form": True})          # the chat panel shows the ticket form
    emit("delta", {"text": answer})
    return {"answer": answer}
