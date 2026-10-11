"""The HTTP contract the frontend relies on: routes, fields, privacy, validation, limits."""
import json
import uuid

from app.main import create_app
from tests.fakes import fake_deps

V1, V2 = str(uuid.uuid4()), str(uuid.uuid4())
H1, H2 = {"X-Visitor-Id": V1}, {"X-Visitor-Id": V2}


def client():
    return create_app(deps=fake_deps()).test_client()


def stream(c, body, headers=H1):
    r = c.post("/api/chat/stream", json=body, headers=headers, buffered=False)
    raw = b"".join(r.response).decode()
    events = []
    for block in raw.strip().split("\n\n"):
        lines = block.split("\n")
        name = [l[7:] for l in lines if l.startswith("event: ")]
        data = [l[6:] for l in lines if l.startswith("data: ")]
        if name:
            events.append((name[0], json.loads(data[0])))
    return r, events


def test_health_lists_providers():
    j = client().get("/api/health").json
    assert j["status"] == "ok" and j["chunks"] == 55 and j["providers"]["llm"] == "fake-llm"


def test_stream_format_and_fields():
    r, ev = stream(client(), {"message": "How long does a refund take?"})
    assert r.headers["Content-Type"].startswith("text/event-stream")
    assert r.headers.get("X-Accel-Buffering") == "no"
    names = [e for e, _ in ev]
    assert names[0] == "step" and "meta" in names and "delta" in names and names[-1] == "done"
    meta, done = dict(ev)["meta"], dict(ev)["done"]
    assert {"query", "sources", "retrieve_ms", "chunks_searched", "route"} <= set(meta)
    assert {"title", "text", "score", "page", "source"} <= set(meta["sources"][0])
    assert {"message_id", "usage", "conversation_id", "title"} <= set(done) and done["conversation_id"]
    assert {"input", "output", "retrieve_ms", "total_ms", "route", "retries"} <= set(done["usage"])


def test_follow_up_keeps_conversation():
    c = client()
    _, ev = stream(c, {"message": "How long does a refund take?"})
    cid = dict(ev)["done"]["conversation_id"]
    _, ev = stream(c, {"message": "how long does it take?", "conversation_id": cid})
    assert dict(ev)["meta"]["query"].startswith("standalone:")
    assert dict(ev)["done"]["conversation_id"] == cid


def test_chats_are_private_per_visitor():
    c = client()
    _, ev = stream(c, {"message": "refund?"})
    cid = dict(ev)["done"]["conversation_id"]
    assert len(c.get("/api/conversations", headers=H1).json) == 1
    assert c.get("/api/conversations", headers=H2).json == []
    assert c.get("/api/conversations").json == []
    assert c.get(f"/api/conversations/{cid}/messages", headers=H2).status_code == 404
    assert c.post("/api/chat/stream", json={"message": "x", "conversation_id": cid}, headers=H2).status_code == 404
    assert c.delete(f"/api/conversations/{cid}", headers=H2).status_code == 404
    msgs = c.get(f"/api/conversations/{cid}/messages", headers=H1).json
    assert [m["role"] for m in msgs] == ["user", "assistant"] and "feedback" in msgs[1]
    assert c.delete(f"/api/conversations/{cid}", headers=H1).status_code == 200
    assert c.get(f"/api/conversations/{cid}/messages", headers=H1).status_code == 404


def test_feedback():
    c = client()
    _, ev = stream(c, {"message": "refund?"})
    mid = dict(ev)["done"]["message_id"]
    assert c.post(f"/api/messages/{mid}/feedback", json={"value": "up"}, headers=H1).json == {"saved": True}
    assert c.post(f"/api/messages/{mid}/feedback", json={"value": None}, headers=H1).status_code == 200
    assert c.post(f"/api/messages/{mid}/feedback", json={"value": "up"}, headers=H2).status_code == 404
    r = c.post(f"/api/messages/{mid}/feedback", json={"value": "meh"}, headers=H1)
    assert r.status_code == 400 and r.json["error"] == "value must be 'up', 'down' or null."


def test_handoff_ticket():
    form = {"name": "Ayesha", "email": "ayesha@example.com", "issue": "My refund hasn't arrived"}
    r = client().post("/api/handoff", json=form, headers=H1)
    assert r.status_code == 200 and r.json["ticket"].startswith("SE-")
    assert r.json["status"] == "waiting" and r.json["position"] == 1 and r.json["conversation_id"]


def test_validation_messages():
    c = client()
    assert c.post("/api/chat/stream", json={"message": "x"}).status_code == 400          # no visitor id
    r = c.post("/api/chat/stream", json={"message": "   "}, headers=H1)
    assert r.status_code == 400 and r.json["error"] == "Message is empty."
    r = c.post("/api/chat/stream", json={"message": "x" * 1200}, headers=H1)
    assert r.status_code == 400 and "under" in r.json["error"]


def test_non_streaming_chat():
    r = client().post("/api/chat", json={"message": "How long does a refund take?"}, headers=H2)
    assert r.status_code == 200 and r.json["answer"].startswith("Refunds") and r.json["message_id"]


def test_admin_stats_need_token():
    assert client().get("/api/admin/stats").status_code == 403


def test_rate_limit_per_visitor():
    c = client()
    codes = [c.post("/api/chat/stream", json={"message": "refund?"}, headers=H1).status_code for _ in range(10)]
    assert codes[:8] == [200] * 8 and codes[8] == 429
