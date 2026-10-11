"""
Live events sent to the browser while the graph runs (Server-Sent Events):

    step   a node started             {"name": "retrieve", ...}
    meta   search done, answer next   {"query", "sources", "route", ...}
    tool   the model used a tool      {"name": "lookup_order"}
    delta  next piece of the answer   {"text": "..."}
    done   answer saved               {"message_id", "usage", "conversation_id", "title"}
"""
from langgraph.config import get_stream_writer


def emit(event, data):
    """Send a live event. Does nothing when a node is called outside a graph run (e.g. in tests)."""
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer({"event": event, "data": data})
