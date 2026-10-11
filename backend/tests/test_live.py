"""WebSockets: customers get pushed updates, agents get "changed" signals, strangers get nothing."""
import json
import queue
import threading
import uuid

from simple_websocket import ConnectionClosed

from app.api import live
from app.core import config
from app.main import create_app
from app.realtime.hub import hub
from tests.fakes import fake_deps

TOKEN = "test-admin-token-123456"
ADMIN = {"Authorization": f"Bearer {TOKEN}"}
FORM = {"name": "Ayesha Khan", "email": "ayesha@example.com", "issue": "My refund hasn't arrived yet"}


class FakeSocket:
    """Stands in for the browser end of a WebSocket."""

    def __init__(self, hello):
        self.hello, self.sent, self.inbox, self.closed = json.dumps(hello), queue.Queue(), queue.Queue(), None

    def receive(self, timeout=None):
        if self.hello:
            hello, self.hello = self.hello, None
            return hello
        if self.closed:
            raise ConnectionClosed()
        try:
            return self.inbox.get(timeout=timeout)
        except queue.Empty:
            return None

    def type(self, payload):          # the browser sends something
        self.inbox.put(json.dumps(payload))

    def send(self, data):
        if self.closed:
            raise ConnectionClosed()
        self.sent.put(json.loads(data))

    def close(self, reason=None, message=None):
        self.closed = (reason, message)

    def next(self, kind="update", timeout=3):
        while True:
            msg = self.sent.get(timeout=timeout)
            if msg["type"] == kind:
                return msg


def setup(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(config, "SUPPORT_AGENTS", 1)
    app = create_app(deps=fake_deps())
    return app, app.test_client()


def run_socket(app, handler, ws):
    def target():
        with app.test_request_context("/ws"):
            handler.__wrapped__(ws)
    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t


def test_customer_gets_pushed_updates(monkeypatch):
    app, c = setup(monkeypatch)
    vid = str(uuid.uuid4())
    t = c.post("/api/handoff", json=FORM, headers={"X-Visitor-Id": vid}).json
    ws = FakeSocket({"visitor_id": vid, "ticket_id": t["id"], "after": 0})
    thread = run_socket(app, live.customer_socket, ws)

    first = ws.next()
    assert first["ticket"]["status"] == "waiting" and first["ticket"]["position"] == 1
    assert first["messages"][0]["content"].startswith(f"Ticket {t['ticket']} opened")

    c.post(f"/api/admin/tickets/{t['id']}/claim", json={"agent": "Ali"}, headers=ADMIN)
    joined = ws.next()
    assert joined["ticket"]["status"] == "active" and joined["messages"][-1]["content"] == "Ali joined the chat."

    c.post(f"/api/admin/tickets/{t['id']}/messages", json={"agent": "Ali", "message": "Hi Ayesha"}, headers=ADMIN)
    reply = ws.next()
    assert [m["content"] for m in reply["messages"]] == ["Hi Ayesha"]          # only what's new

    c.post(f"/api/admin/tickets/{t['id']}/close", json={"agent": "Ali"}, headers=ADMIN)
    assert ws.next()["ticket"]["status"] == "closed"
    thread.join(timeout=3)
    assert not thread.is_alive()                                                # socket finished cleanly


def test_queue_position_moves_live(monkeypatch):
    app, c = setup(monkeypatch)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    ta = c.post("/api/handoff", json=FORM, headers={"X-Visitor-Id": a}).json
    tb = c.post("/api/handoff", json=FORM, headers={"X-Visitor-Id": b}).json
    ws = FakeSocket({"visitor_id": b, "ticket_id": tb["id"]})
    run_socket(app, live.customer_socket, ws)
    assert ws.next()["ticket"]["position"] == 2
    c.post(f"/api/handoff/{ta['id']}/cancel", headers={"X-Visitor-Id": a})      # the person ahead leaves
    assert ws.next()["ticket"]["position"] == 1
    ws.closed = (1000, "bye")
    hub.publish({"type": "ticket", "ticket_id": 0})                             # next send fails -> handler ends


def test_strangers_and_bad_tokens_are_refused(monkeypatch):
    app, c = setup(monkeypatch)
    t = c.post("/api/handoff", json=FORM, headers={"X-Visitor-Id": str(uuid.uuid4())}).json
    ws = FakeSocket({"visitor_id": str(uuid.uuid4()), "ticket_id": t["id"]})
    run_socket(app, live.customer_socket, ws).join(timeout=3)
    assert ws.closed[0] == 1008 and ws.sent.empty()
    ws = FakeSocket({"token": "wrong"})
    run_socket(app, live.admin_socket, ws).join(timeout=3)
    assert ws.closed[0] == 1008


def test_agents_hear_about_changes(monkeypatch):
    app, c = setup(monkeypatch)
    ws = FakeSocket({"token": TOKEN})
    run_socket(app, live.admin_socket, ws)
    ws.next("ready")
    t = c.post("/api/handoff", json=FORM, headers={"X-Visitor-Id": str(uuid.uuid4())}).json
    assert ws.next("changed") == {"type": "changed", "kind": "ticket", "ticket_id": t["id"]}
    ws.closed = (1000, "bye")
    hub.publish({"type": "ticket", "ticket_id": 0})


def test_typing_indicator_both_ways(monkeypatch):
    app, c = setup(monkeypatch)
    vid = str(uuid.uuid4())
    t = c.post("/api/handoff", json=FORM, headers={"X-Visitor-Id": vid}).json
    customer = FakeSocket({"visitor_id": vid, "ticket_id": t["id"]})
    agent = FakeSocket({"token": TOKEN})
    run_socket(app, live.customer_socket, customer)
    run_socket(app, live.admin_socket, agent)
    customer.next()
    agent.next("ready")

    customer.type({"type": "typing", "on": True})
    assert agent.next("typing") == {"type": "typing", "ticket_id": t["id"], "on": True}

    agent.type({"type": "typing", "ticket_id": t["id"], "agent": "Ali", "on": True})
    assert customer.next("typing") == {"type": "typing", "name": "Ali", "on": True}

    # someone else's ticket: this customer doesn't hear about it
    agent.type({"type": "typing", "ticket_id": t["id"] + 99, "agent": "Ali", "on": True})
    agent.type({"type": "typing", "ticket_id": t["id"], "agent": "Ali", "on": False})
    assert customer.next("typing") == {"type": "typing", "name": "Ali", "on": False}
    customer.closed = agent.closed = (1000, "bye")
