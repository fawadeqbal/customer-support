"""Decide what kind of message this is, with simple rules (no model call)."""
import re

from app.graph.events import emit

# Clear requests for a person skip the model entirely (fast, free). Anything subtler, the model
# notices itself and calls the open_support_ticket tool (see app/tools/support.py).
HANDOFF = re.compile(
    r"\b(talk|speak|chat|connect|transfer|put me through|contact)\b.*"
    r"\b(person|human|agent|someone|somebody|representative|rep|staff|support( team)?|customer (care|service|support)|team|manager|supervisor)\b"
    r"|\b(real|live|actual)\s+(person|human|agent)\b"
    r"|^\s*(i\s+)?(want|need|would like|wanna)\s+to\s+(talk|speak)\s*(to\s+(someone|somebody|you(r)? (team|people)))?[\s.!]*$"
    r"|\b(human|agent|representative)\s*(please|plz|pls)\b"
    r"|\b(insaan|insan|banda|bande|agent|representative|staff|team)\s*(se|sy|say)\s*(baat|bat|rabta)",
    re.I,
)
GREETING = re.compile(
    r"^\s*(hi|hello|hey|salam|salaam|as+ala+m[\s-]*[ou]?[\s-]*alai?kum|aoa|thanks|thank you|thx|shukriya"
    r"|jazakallah|ok|okay|bye|good (morning|evening))[\s!.]*$",
    re.I,
)


def classify(state, deps=None):
    q = state["question"]
    route = "handoff" if HANDOFF.search(q) else "greeting" if GREETING.match(q) else "question"
    emit("step", {"name": "classify", "route": route})
    return {"route": route, "query": q}
