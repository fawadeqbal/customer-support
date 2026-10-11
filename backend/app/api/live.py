"""
WebSockets: the server pushes changes the moment they happen (no refreshing, no polling).

    /ws/support   a customer's open ticket: place in the queue, agent replies, status lines, typing
    /ws/admin     agents: "something changed" -> the console reloads the list / open ticket; typing

The browser sends one JSON "hello" first (so ids and tokens never appear in URLs or logs):
    customer  {"visitor_id": "...", "ticket_id": 7, "after": <newest message id on screen>}
    agent     {"token": "<ADMIN_TOKEN>"}
Browser -> server, any time after that:
    customer  {"type": "typing", "on": true}
    agent     {"type": "typing", "ticket_id": 7, "agent": "Ali", "on": true}
Server -> browser:
    {"type": "update", "ticket": {...}, "messages": [...]}     customer
    {"type": "typing", "name": "Ali", "on": true}               customer: the agent is typing
    {"type": "changed", "kind": "ticket" | "message", "ticket_id": 7}   agent
    {"type": "typing", "ticket_id": 7, "on": true}               agent: that customer is typing
    {"type": "ping"}                                             every 25 s, keeps proxies from closing it
Events come from app/support/desk.py through app/realtime/hub.py.
"""
import hmac
import json
import logging
import queue
import time

from flask import current_app
from flask_sock import Sock
from simple_websocket import ConnectionClosed

from app.core import config
from app.realtime.hub import hub
from app.support import desk

log = logging.getLogger(__name__)
sock = Sock()
PING_SECONDS = 25
LISTEN_SECONDS = 0.25      # how long each loop waits for the browser before checking the hub


def _hello(ws):
    try:
        return json.loads(ws.receive(timeout=10) or "{}")
    except (ValueError, TypeError):
        return {}


def _send(ws, payload):
    ws.send(json.dumps(payload, default=str))


def _loop(ws, q, on_client, on_events):
    """Both directions on one thread: read the browser (typing), forward hub events, ping.
    on_events(batch) returning True ends the socket."""
    last_ping = time.monotonic()
    while True:
        raw = ws.receive(timeout=LISTEN_SECONDS)
        if raw:
            try:
                msg = json.loads(raw)
            except ValueError:
                msg = None
            if isinstance(msg, dict):
                on_client(msg)
        batch = []
        while True:                      # several changes at once -> one update
            try:
                batch.append(q.get_nowait())
            except queue.Empty:
                break
        if batch and on_events(batch):
            return
        if time.monotonic() - last_ping > PING_SECONDS:
            _send(ws, {"type": "ping"})
            last_ping = time.monotonic()


@sock.route("/ws/support")
def customer_socket(ws):
    deps = current_app.extensions["deps"]
    hello = _hello(ws)
    try:
        ticket_id = int(hello.get("ticket_id"))
        after = int(hello.get("after") or 0)
    except (TypeError, ValueError):
        ws.close(reason=1008, message="Bad hello")
        return
    ticket = deps.tickets.get(ticket_id)
    if ticket is None or ticket.get("visitor_id") != hello.get("visitor_id"):
        ws.close(reason=1008, message="Ticket not found")
        return

    def push():
        nonlocal after
        current = deps.tickets.get(ticket_id)
        new = []
        if current.get("conversation_id"):
            new = [m for m in deps.conversations.messages(current["conversation_id"], after=after)
                   if m["role"] in ("agent", "system")]
        if new:
            after = new[-1]["id"]
        _send(ws, {"type": "update", "ticket": desk.public(deps, current), "messages": new})
        return current["status"]

    def from_customer(msg):
        if msg.get("type") == "typing":
            hub.publish({"type": "typing", "ticket_id": ticket_id, "who": "customer", "on": bool(msg.get("on"))})

    def on_events(batch):
        for e in batch:
            if e["type"] == "typing" and e["who"] == "agent" and e["ticket_id"] == ticket_id:
                _send(ws, {"type": "typing", "name": e["name"], "on": e["on"]})
        if any(e["type"] != "typing" for e in batch):
            return push() == "closed"      # every queue change can move this customer's place in line
        return False

    q = hub.subscribe()
    try:
        if push() == "closed":
            return
        _loop(ws, q, from_customer, on_events)
    except ConnectionClosed:
        pass
    except Exception:
        log.exception("customer socket failed")
    finally:
        hub.unsubscribe(q)


@sock.route("/ws/admin")
def admin_socket(ws):
    token = str(_hello(ws).get("token", ""))
    if not config.ADMIN_TOKEN or not hmac.compare_digest(token, config.ADMIN_TOKEN):
        ws.close(reason=1008, message="Not allowed")
        return
    def from_agent(msg):
        if msg.get("type") == "typing":
            try:
                ticket_id = int(msg.get("ticket_id"))
            except (TypeError, ValueError):
                return
            hub.publish({"type": "typing", "ticket_id": ticket_id, "who": "agent",
                         "name": str(msg.get("agent") or "Support")[:40], "on": bool(msg.get("on"))})

    def on_events(batch):
        for e in batch:
            if e["type"] == "typing":
                if e["who"] == "customer":
                    _send(ws, {"type": "typing", "ticket_id": e["ticket_id"], "on": e["on"]})
            else:
                _send(ws, {"type": "changed", "kind": e["type"], "ticket_id": e["ticket_id"]})
        return False

    q = hub.subscribe()
    try:
        _send(ws, {"type": "ready"})
        _loop(ws, q, from_agent, on_events)
    except ConnectionClosed:
        pass
    except Exception:
        log.exception("admin socket failed")
    finally:
        hub.unsubscribe(q)
