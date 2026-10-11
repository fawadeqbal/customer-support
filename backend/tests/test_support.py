"""The human support queue: positions, wait estimates, agent chat, privacy and admin protection."""
import uuid

from app.core import config
from app.main import create_app
from tests.fakes import fake_deps

TOKEN = "test-admin-token-123456"
ADMIN = {"Authorization": f"Bearer {TOKEN}"}


FORM = {"name": "Ayesha Khan", "email": "ayesha@example.com", "issue": "My refund hasn't arrived yet"}


def visitor():
    return {"X-Visitor-Id": str(uuid.uuid4())}


def setup(monkeypatch, agents=1, minutes=5):
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(config, "SUPPORT_AGENTS", agents)
    monkeypatch.setattr(config, "AVG_HANDLE_MINUTES", minutes)
    deps = fake_deps()
    return create_app(deps=deps).test_client(), deps


def test_queue_positions_and_wait(monkeypatch):
    c, _ = setup(monkeypatch, agents=1, minutes=5)
    a, b, d = visitor(), visitor(), visitor()
    ta = c.post("/api/handoff", json=FORM, headers=a).json
    tb = c.post("/api/handoff", json=FORM, headers=b).json
    td = c.post("/api/handoff", json=FORM, headers=d).json
    # 1 agent, free: first in line is picked up soon, the others wait behind
    assert (ta["position"], ta["wait_minutes"], ta["agents_busy"]) == (1, 1, False)
    assert (td["position"], td["ahead"]) == (3, 2) and td["wait_minutes"] == 10

    # the agent takes A: now everyone else waits for that chat to finish
    r = c.post(f"/api/admin/tickets/{ta['id']}/claim", json={"agent": "Ali"}, headers=ADMIN)
    assert r.status_code == 200 and r.json["status"] == "active"
    sb = c.get(f"/api/handoff/{tb['id']}", headers=b).json
    assert (sb["position"], sb["agents_busy"], sb["wait_minutes"]) == (1, True, 5)

    # a second agent can't take the same ticket
    r = c.post(f"/api/admin/tickets/{ta['id']}/claim", json={"agent": "Sara"}, headers=ADMIN)
    assert r.status_code == 409 and "Ali" in r.json["error"]


def test_agent_chat_round_trip(monkeypatch):
    c, deps = setup(monkeypatch)
    v = visitor()
    t = c.post("/api/handoff", json=FORM, headers=v).json
    # replying before taking the ticket is refused
    assert c.post(f"/api/admin/tickets/{t['id']}/messages", json={"agent": "Ali", "message": "hi"},
                  headers=ADMIN).status_code == 409
    c.post(f"/api/admin/tickets/{t['id']}/claim", json={"agent": "Ali"}, headers=ADMIN)
    c.post(f"/api/admin/tickets/{t['id']}/messages", json={"agent": "Ali", "message": "How can I help?"},
           headers=ADMIN)
    assert c.post(f"/api/handoff/{t['id']}/messages", json={"message": "My refund is late"},
                  headers=v).status_code == 200

    # the customer polls and gets the status lines + the agent's reply
    s = c.get(f"/api/handoff/{t['id']}?after=0", headers=v).json
    roles = [(m["role"], m["content"]) for m in s["messages"]]
    assert ("system", "Ali joined the chat.") in roles and ("agent", "How can I help?") in roles
    assert all(r != "user" for r, _ in roles)            # own messages are already on screen
    last = s["messages"][-1]["id"]
    assert c.get(f"/api/handoff/{t['id']}?after={last}", headers=v).json["messages"] == []

    # while a person handles it, the assistant stays out of this chat
    r = c.post("/api/chat/stream", json={"conversation_id": t["conversation_id"], "message": "hello?"}, headers=v)
    assert r.status_code == 409 and r.json["ticket"] == t["id"]

    # the admin sees the whole chat, then closes it; the assistant answers again
    d = c.get(f"/api/admin/tickets/{t['id']}", headers=ADMIN).json
    assert [m["role"] for m in d["messages"]].count("user") == 1 and d["agent"] == "Ali"
    assert c.post(f"/api/admin/tickets/{t['id']}/close", json={"agent": "Ali"}, headers=ADMIN).json["status"] == "closed"
    assert c.post(f"/api/handoff/{t['id']}/messages", json={"message": "still there?"}, headers=v).status_code == 409
    r = c.post("/api/chat/stream", json={"conversation_id": t["conversation_id"], "message": "thanks"}, headers=v)
    assert r.status_code == 200
    # agent / system lines never reach the model's memory
    assert all(m["role"] in ("user", "assistant") for m in deps.conversations.history(t["conversation_id"], 10))


def test_customer_can_leave_and_cant_see_others(monkeypatch):
    c, _ = setup(monkeypatch)
    v, other = visitor(), visitor()
    t = c.post("/api/handoff", json=FORM, headers=v).json
    assert c.get(f"/api/handoff/{t['id']}", headers=other).status_code == 404
    assert c.post(f"/api/handoff/{t['id']}/cancel", headers=other).status_code == 404
    assert c.post(f"/api/handoff/{t['id']}/cancel", headers=v).json["status"] == "closed"
    cur = c.get(f"/api/handoff/current?conversation_id={t['conversation_id']}", headers=v).json
    assert cur == {"ticket": None}


def test_one_open_ticket_per_chat(monkeypatch):
    c, _ = setup(monkeypatch)
    v = visitor()
    t1 = c.post("/api/handoff", json=FORM, headers=v).json
    t2 = c.post("/api/handoff", json={**FORM, "conversation_id": t1["conversation_id"]}, headers=v).json
    assert t1["id"] == t2["id"]


def test_admin_routes_need_the_token(monkeypatch):
    c, _ = setup(monkeypatch)
    assert c.get("/api/admin/tickets").status_code == 403
    assert c.get("/api/admin/tickets", headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert c.get("/api/admin/tickets", headers=ADMIN).status_code == 200
    s = c.get("/api/admin/stats", headers=ADMIN).json
    assert s["agents_on_shift"] == 1 and s["waiting"] == 0
    r = c.post("/api/admin/tickets/1/claim", json={"agent": ""}, headers=ADMIN)
    assert r.status_code in (400, 404)


def test_talk_to_a_person_in_chat_asks_for_the_form(monkeypatch):
    c, deps = setup(monkeypatch)
    r = c.post("/api/chat/stream", json={"message": "I want to talk to a person"}, headers=visitor(), buffered=False)
    raw = b"".join(r.response).decode()
    assert 'event: handoff\ndata: {"form": true}' in raw
    assert deps.tickets.rows == {}


def test_ticket_form_validation(monkeypatch):
    c, _ = setup(monkeypatch)
    v = visitor()
    cases = [({}, "Please enter your name."),
             ({**FORM, "email": "ayesha@"}, "Please enter a valid email address."),
             ({**FORM, "issue": "hi"}, "Please describe the issue in a few words.")]
    for body, message in cases:
        r = c.post("/api/handoff", json=body, headers=v)
        assert r.status_code == 400 and r.json["error"] == message, r.json


def test_ticket_with_files(monkeypatch):
    import io
    c, _ = setup(monkeypatch)
    v = visitor()
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    data = {**FORM, "files": [(io.BytesIO(png), "screenshot.png"), (io.BytesIO(b"order SE10482931"), "notes.txt")]}
    t = c.post("/api/handoff", data=data, headers=v, content_type="multipart/form-data").json
    d = c.get(f"/api/admin/tickets/{t['id']}", headers=ADMIN).json
    assert d["customer_name"] == "Ayesha Khan" and d["customer_email"] == "ayesha@example.com"
    assert [f["filename"] for f in d["files"]] == ["screenshot.png", "notes.txt"] and d["file_count"] == 2
    assert "2 files attached" in d["messages"][-1]["content"]
    f = c.get(f"/api/admin/files/{d['files'][0]['id']}", headers=ADMIN)
    assert f.status_code == 200 and f.data == png and f.mimetype == "image/png"
    assert c.get(f"/api/admin/files/{d['files'][0]['id']}").status_code == 403      # admins only

    bad = {**FORM, "files": [(io.BytesIO(b"MZ"), "virus.exe")]}
    r = c.post("/api/handoff", data=bad, headers=visitor(), content_type="multipart/form-data")
    assert r.status_code == 400 and "image" in r.json["error"]
    many = {**FORM, "files": [(io.BytesIO(b"x"), f"{i}.txt") for i in range(4)]}
    r = c.post("/api/handoff", data=many, headers=visitor(), content_type="multipart/form-data")
    assert r.status_code == 400 and "up to 3" in r.json["error"]
