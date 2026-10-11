"""Nodes that read and write the conversation memory."""
import logging
import threading
import time

from app.core import config
from app.graph.events import emit

log = logging.getLogger(__name__)


def load_memory(state, deps):
    """Recent messages + running summary, and a fresh scratchpad for this run."""
    conv = state["conversation"]
    history = deps.conversations.history(conv["id"], config.MEMORY_TURNS) if conv["id"] else []
    return {"history": history, "summary": conv.get("summary", ""), "attempts": 0,
            "results": [], "tools": [], "usage": {"input": 0, "output": 0},
            "started": time.perf_counter(), "retrieve_ms": 0}


def save(state, deps):
    """Store question + answer; update the running summary in the background."""
    conv = dict(state["conversation"])
    if conv["id"] is None:            # new chat: only saved once there is an answer
        conv.update(deps.conversations.create(conv["title"], conv.get("visitor_id")))
    usage = {
        **state["usage"],
        "retrieve_ms": state["retrieve_ms"],
        "total_ms": round((time.perf_counter() - state["started"]) * 1000),
        "query": state.get("query", state["question"]),
        "route": state["route"],
        "retries": state.get("attempts", 0),
        "tools": state.get("tools", []),
    }
    deps.conversations.add_message(conv["id"], "user", state["question"])
    message_id = deps.conversations.add_message(conv["id"], "assistant", state["answer"],
                                                sources=state["results"], usage=usage)
    threading.Thread(target=update_summary, args=(deps, conv["id"]), daemon=True).start()
    emit("done", {"message_id": message_id, "usage": usage,
                  "conversation_id": conv["id"], "title": conv["title"]})
    return {"conversation": conv, "message_id": message_id, "usage": usage}


def update_summary(deps, conversation_id):
    """Fold messages that left the word-for-word window into the running summary."""
    try:
        previous, new_messages = deps.conversations.messages_to_summarize(conversation_id, config.MEMORY_TURNS)
        if new_messages:
            summary = deps.assistant.summarize(previous, new_messages)
            deps.conversations.save_summary(conversation_id, summary, new_messages[-1]["id"])
    except Exception:
        log.exception("summary update failed")
