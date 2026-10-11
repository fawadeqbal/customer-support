"""ChatState: the shared notebook every node of the graph reads and updates."""
from typing import TypedDict


class ChatState(TypedDict, total=False):
    # input
    question: str
    conversation: dict        # {"id": uuid or None for a new chat, "title", "summary", "visitor_id"}
    # filled in by the nodes
    history: list             # recent messages (load_memory)
    summary: str              # running summary of older messages
    route: str                # "question" | "greeting" | "handoff" (classify)
    query: str                # what we actually searched for (rewrite / broaden)
    results: list             # retrieved chunks (retrieve)
    attempts: int             # retrieval retries done
    answer: str               # final reply (generate / handoff)
    usage: dict               # tokens + timings
    tools: list               # tools the model used
    message_id: int           # id of the saved answer (save)
    started: float
    retrieve_ms: int
