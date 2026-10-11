"""
The support desk: a queue of tickets in front of a few human agents.

    customer asks for a person  -> open_ticket()     ticket waits in the queue
    agent clicks "Take"          -> claim()           "Ali joined the chat"
    both sides write             -> customer_message() / agent_message()
    agent clicks "Close"         -> close()           the assistant takes over again

queue_info() tells the customer where they are:
    position     1 = next in line
    wait_minutes rough estimate from free agents and the average chat length
    agents_busy  True when every agent is already in a chat
"""
import math

from app.core import config
from app.realtime.hub import hub

OPEN = ("waiting", "active")


class DeskError(Exception):
    """Something the caller did wrong (shown to the user as is)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _note(deps, ticket, text):
    """A status line in the chat ("Ali joined the chat"). Old tickets may have no chat."""
    if ticket.get("conversation_id"):
        deps.conversations.add_message(ticket["conversation_id"], "system", text)


def _changed(ticket_id, kind="ticket"):
    """Tell every open WebSocket (customers and agents) that something happened."""
    hub.publish({"type": kind, "ticket_id": ticket_id})


def queue_info(deps, ticket):
    if ticket["status"] != "waiting":
        return {"position": 0, "ahead": 0, "wait_minutes": 0, "agents_busy": False}
    waiting = deps.tickets.waiting_ids()
    position = waiting.index(ticket["id"]) + 1 if ticket["id"] in waiting else len(waiting)
    agents = max(1, config.SUPPORT_AGENTS)
    free = max(0, agents - deps.tickets.active_count())
    measured = deps.tickets.avg_handle_minutes()   # None until agents have closed some chats
    avg = config.AVG_HANDLE_MINUTES if measured is None else max(1.0, measured)
    if position <= free:
        wait = 1                                              # an agent is free, just has to pick it up
    else:
        wait = math.ceil((position - free) / agents * avg)    # each agent clears one chat per `avg` minutes
    return {"position": position, "ahead": position - 1, "wait_minutes": max(1, wait), "agents_busy": free == 0}


def public(deps, ticket):
    """What the customer's chat panel needs."""
    return {
        "id": ticket["id"], "ticket": ticket["ticket"], "status": ticket["status"], "agent": ticket.get("agent"),
        "conversation_id": ticket.get("conversation_id"), "created_at": ticket.get("created_at"),
        **queue_info(deps, ticket),
    }


def open_ticket(deps, conversation, visitor_id, reason, contact=None, files=()):
    """Put this chat in the queue (or return its ticket if it already is). conversation may be None.
    contact: {"name", "email", "issue"} from the form; files: [(filename, content_type, bytes)]."""
    if conversation is None:
        conversation = deps.conversations.create((reason or "Talk to a person")[:60], visitor_id)
    existing = deps.tickets.open_for(conversation["id"])
    if existing:
        return existing, conversation
    ticket = deps.tickets.create(conversation["id"], visitor_id, reason, contact)
    for name, content_type, data in files:
        deps.tickets.add_file(ticket["id"], name, content_type, data)
    attached = f" · {len(files)} file{'s' if len(files) != 1 else ''} attached" if files else ""
    deps.conversations.add_message(conversation["id"], "system", f"Ticket {ticket['ticket']} opened{attached}")
    _changed(ticket["id"])
    return deps.tickets.get(ticket["id"]), conversation


def _open(deps, ticket_id):
    ticket = deps.tickets.get(ticket_id)
    if ticket is None:
        raise DeskError("Ticket not found.", 404)
    if ticket["status"] not in OPEN:
        raise DeskError("This ticket is already closed.", 409)
    return ticket


def customer_message(deps, ticket, text):
    if ticket["status"] not in OPEN:
        raise DeskError("This ticket is closed. The assistant is answering again.", 409)
    message_id = deps.conversations.add_message(ticket["conversation_id"], "user", text)
    _changed(ticket["id"], "message")
    return message_id


def customer_leave(deps, ticket):
    if ticket["status"] not in OPEN:
        return ticket
    closed = deps.tickets.close(ticket["id"], "customer")
    _note(deps, ticket, "You left the queue. The assistant is answering again.")
    _changed(ticket["id"])
    return closed


def claim(deps, ticket_id, agent):
    ticket = _open(deps, ticket_id)
    if ticket["status"] == "active":
        raise DeskError(f"{ticket['agent']} already took this ticket.", 409)
    claimed = deps.tickets.claim(ticket_id, agent)
    if claimed is None:
        raise DeskError("Someone else took this ticket first.", 409)
    _note(deps, claimed, f"{agent} joined the chat.")
    _changed(ticket_id)
    return claimed


def agent_message(deps, ticket_id, agent, text):
    ticket = _open(deps, ticket_id)
    if ticket["status"] != "active":
        raise DeskError("Take the ticket before replying.", 409)
    if not ticket.get("conversation_id"):
        raise DeskError("This ticket has no chat to reply in.", 409)
    message_id = deps.conversations.add_message(ticket["conversation_id"], "agent", text, author=agent)
    _changed(ticket_id, "message")
    return message_id


def close(deps, ticket_id, agent):
    _open(deps, ticket_id)
    closed = deps.tickets.close(ticket_id, agent)
    _note(deps, closed, f"{agent} closed the chat. The assistant is answering again.")
    _changed(ticket_id)
    return closed
