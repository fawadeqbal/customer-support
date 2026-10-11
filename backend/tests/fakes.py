"""In-memory stand-ins for the knowledge base, the model and the database, so tests need none of them."""
import datetime
import itertools
import uuid

from app.core.security import is_valid_id
from app.graph.deps import Deps


class _Named:
    def __init__(self, name):
        self.name = name


class FakeKnowledge:
    chunk_count = 55
    embeddings, store, reranker = _Named("fake-embeddings"), _Named("fake-store"), _Named("fake-reranker")

    def __init__(self):
        self.searches = []

    def search(self, query, top_k=4, min_score=0.3, candidates=20):
        self.searches.append((query, round(min_score, 3), candidates))
        if "ceo" in query.lower():
            return []
        return [{"title": "Refund Timelines", "text": "Refund Timelines\nWallet within 24 hours...",
                 "score": 0.71, "source": "handbook.pdf", "page": 7}]


class FakeAssistant:
    chat, fast = _Named("fake-llm"), _Named("fake-fast-llm")

    def rewrite_query(self, question, history, force=False):
        if history or force:
            return f"standalone: {question}", {"input": 30, "output": 8}
        return question, {"input": 0, "output": 0}

    def stream(self, question, chunks, history, summary=""):
        if "SE1" in question:
            yield "tool", "lookup_order"
        if "complaint" in question.lower():      # the real model calls this when a person is needed
            yield "tool", "open_support_ticket"
        for piece in ["Refunds ", "take **2-3** ", "working days. ", "ریفنڈ"]:
            yield "delta", piece
        yield "usage", {"input": 900, "output": 40}

    def summarize(self, previous, messages):
        return "summary"


class InMemoryConversations:
    def __init__(self):
        self.convs, self.msgs, self._ids = {}, [], itertools.count(1)

    def _public(self, c):
        return {k: c[k] for k in ("id", "title", "updated_at", "summary")}

    def create(self, title, visitor_id):
        c = {"id": str(uuid.uuid4()), "title": title, "summary": "", "visitor_id": visitor_id,
             "updated_at": datetime.datetime.now().isoformat()}
        self.convs[c["id"]] = c
        return self._public(c)

    def get(self, conversation_id, visitor_id):
        c = self.convs.get(str(conversation_id)) if is_valid_id(conversation_id) else None
        return self._public(c) if c and c["visitor_id"] == visitor_id else None

    def list(self, visitor_id, limit=50):
        return [self._public(c) for c in self.convs.values() if c["visitor_id"] == visitor_id]

    def delete(self, conversation_id, visitor_id):
        if self.get(conversation_id, visitor_id):
            del self.convs[conversation_id]
            self.msgs = [m for m in self.msgs if m["conversation_id"] != conversation_id]

    def add_message(self, conversation_id, role, content, sources=None, usage=None, author=None):
        assert conversation_id, "messages need a chat"
        m = {"id": next(self._ids), "conversation_id": conversation_id, "role": role, "content": content,
             "sources": sources, "usage": usage, "feedback": None, "author": author,
             "created_at": datetime.datetime.now().isoformat()}
        self.msgs.append(m)
        return m["id"]

    def messages(self, conversation_id, after=0):
        return [{k: m[k] for k in ("id", "role", "content", "sources", "usage", "feedback", "author", "created_at")}
                for m in self.msgs if m["conversation_id"] == conversation_id and m["id"] > after]

    def history(self, conversation_id, turns):
        return [{"role": m["role"], "content": m["content"]} for m in self.msgs
                if m["conversation_id"] == conversation_id and m["role"] in ("user", "assistant")][-turns * 2:]

    def messages_to_summarize(self, conversation_id, keep_turns):
        return "", []

    def save_summary(self, *args):
        pass

    def questions_today(self):
        return sum(1 for m in self.msgs if m["role"] == "assistant")


class InMemoryFeedback:
    def __init__(self, conversations):
        self.conversations = conversations

    def set_feedback(self, message_id, visitor_id, value):
        for m in self.conversations.msgs:
            owner = self.conversations.convs.get(m["conversation_id"], {}).get("visitor_id")
            if m["id"] == message_id and m["role"] == "assistant" and owner == visitor_id:
                m["feedback"] = value
                return True
        return False

    def stats(self):
        return {"questions_today": self.conversations.questions_today()}


class InMemoryTickets:
    """Same methods as app.db.repositories.tickets.TicketRepository."""

    def __init__(self, conversations):
        self.conversations, self.rows, self._ids, self.file_rows = conversations, {}, itertools.count(1), []
        self.handle_minutes = None

    def _out(self, t):
        if t is None:
            return None
        conv = self.conversations.convs.get(t["conversation_id"] or "", {})
        return {**t, "ticket": f"SE-{48000 + t['id']}", "title": conv.get("title"),
                "file_count": sum(f["handoff_id"] == t["id"] for f in self.file_rows)}

    def create(self, conversation_id, visitor_id, reason, contact=None):
        contact = contact or {}
        t = {"id": next(self._ids), "conversation_id": conversation_id, "visitor_id": visitor_id,
             "status": "waiting", "reason": reason, "agent": None, "closed_by": None,
             "customer_name": contact.get("name"), "customer_email": contact.get("email"), "issue": contact.get("issue"),
             "created_at": datetime.datetime.now().isoformat(), "claimed_at": None, "closed_at": None}
        self.rows[t["id"]] = t
        return self._out(t)

    def add_file(self, ticket_id, filename, content_type, data):
        self.file_rows.append({"id": len(self.file_rows) + 1, "handoff_id": ticket_id, "filename": filename,
                               "content_type": content_type, "size_bytes": len(data), "data": data})

    def files(self, ticket_id):
        return [{k: f[k] for k in ("id", "filename", "content_type", "size_bytes")}
                for f in self.file_rows if f["handoff_id"] == ticket_id]

    def get_file(self, file_id):
        return next((f for f in self.file_rows if f["id"] == file_id), None)

    def get(self, ticket_id):
        return self._out(self.rows.get(ticket_id))

    def open_for(self, conversation_id):
        hits = [t for t in self.rows.values()
                if t["conversation_id"] == conversation_id and t["status"] in ("waiting", "active")]
        return self._out(hits[-1]) if hits and conversation_id else None

    def list(self, closed_hours=24):
        return [self._out(t) for t in self.rows.values()]

    def waiting_ids(self):
        return [t["id"] for t in self.rows.values() if t["status"] == "waiting"]

    def active_count(self):
        return sum(t["status"] == "active" for t in self.rows.values())

    def avg_handle_minutes(self, last=20):
        return self.handle_minutes

    def claim(self, ticket_id, agent):
        t = self.rows.get(ticket_id)
        if not t or t["status"] != "waiting":
            return None
        t.update(status="active", agent=agent, claimed_at=datetime.datetime.now().isoformat())
        return self._out(t)

    def close(self, ticket_id, closed_by):
        t = self.rows.get(ticket_id)
        if not t or t["status"] == "closed":
            return None
        t.update(status="closed", closed_by=closed_by, closed_at=datetime.datetime.now().isoformat())
        return self._out(t)

    def counts(self):
        return {"waiting": len(self.waiting_ids()), "active": self.active_count(),
                "closed_today": sum(t["status"] == "closed" for t in self.rows.values()), "avg_wait_seconds": None}


def fake_deps():
    conversations = InMemoryConversations()
    return Deps(knowledge=FakeKnowledge(), assistant=FakeAssistant(), conversations=conversations,
                feedback=InMemoryFeedback(conversations), tickets=InMemoryTickets(conversations))
