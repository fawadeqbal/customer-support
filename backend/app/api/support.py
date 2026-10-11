"""
The customer's side of "talk to a person" (the agent's side is in admin.py).

    POST /api/handoff                         open a ticket: form fields name, email, issue,
                                              conversation_id? + up to 3 files (multipart) or JSON
    GET  /api/handoff/current?conversation_id  the open ticket of a chat, or {"ticket": null}
    GET  /api/handoff/<id>?after=<message id>  place in the queue + new agent/system messages (polled)
    POST /api/handoff/<id>/messages           write to the agent    {message}
    POST /api/handoff/<id>/cancel             leave the queue / end the chat
A visitor can only see and use their own tickets.
"""
from pathlib import Path

from flask import Blueprint, jsonify, request

from app.api.common import deps, error, limiters, visitor_id
from app.api.schemas import HandoffRequest, TicketMessageRequest, parse
from app.core import config
from app.support import desk

bp = Blueprint("support", __name__)


def _own_ticket(ticket_id):
    """(ticket, None) if it belongs to this visitor, else (None, error response)."""
    vid = visitor_id()
    ticket = deps().tickets.get(ticket_id) if vid else None
    if ticket is None or ticket.get("visitor_id") != vid:
        return None, error("Ticket not found.", 404)
    return ticket, None


@bp.post("/api/handoff")
def join_queue():
    vid = visitor_id()
    if not vid:
        return error("Missing visitor id.", 400)
    if limiters()[1].retry_after(f"handoff:{vid}"):
        return error("Please wait a moment before trying again.", 429)
    data = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    body, msg = parse(HandoffRequest, data)
    if msg:
        return error(msg, 400)
    files, msg = _read_files()
    if msg:
        return error(msg, 400)
    conversation = deps().conversations.get(body.conversation_id, vid) if body.conversation_id else None
    contact = {"name": body.name, "email": body.email, "issue": body.issue}
    ticket, conversation = desk.open_ticket(deps(), conversation, vid, body.issue[:500], contact, files)
    return jsonify(desk.public(deps(), ticket))


def _read_files():
    """([(filename, content_type, bytes)], None) or (None, error message)."""
    uploads = [f for f in request.files.getlist("files") if f and f.filename]
    if len(uploads) > config.TICKET_MAX_FILES:
        return None, f"You can attach up to {config.TICKET_MAX_FILES} files."
    limit = config.TICKET_MAX_FILE_MB * 1024 * 1024
    files = []
    for f in uploads:
        name = Path(f.filename).name[:120]
        content_type = config.TICKET_FILE_TYPES.get(Path(name).suffix.lower())
        if not content_type:
            return None, f"{name}: please attach an image (PNG, JPG, WEBP, GIF), a PDF or a text file."
        data = f.read(limit + 1)
        if len(data) > limit:
            return None, f"{name} is larger than {config.TICKET_MAX_FILE_MB} MB."
        if data:
            files.append((name, content_type, data))
    return files, None


@bp.get("/api/handoff/current")
def current_ticket():
    vid = visitor_id()
    conversation_id = request.args.get("conversation_id", "")
    if not vid or not deps().conversations.get(conversation_id, vid):
        return jsonify(ticket=None)
    ticket = deps().tickets.open_for(conversation_id)
    return jsonify(desk.public(deps(), ticket) if ticket else {"ticket": None})


@bp.get("/api/handoff/<int:ticket_id>")
def ticket_status(ticket_id):
    ticket, err = _own_ticket(ticket_id)
    if err:
        return err
    after = request.args.get("after", 0, type=int)
    new = [m for m in deps().conversations.messages(ticket["conversation_id"], after=after)
           if m["role"] in ("agent", "system")] if ticket.get("conversation_id") else []
    return jsonify({**desk.public(deps(), ticket), "messages": new})


@bp.post("/api/handoff/<int:ticket_id>/messages")
def customer_message(ticket_id):
    ticket, err = _own_ticket(ticket_id)
    if err:
        return err
    if limiters()[1].retry_after(f"visitor:{ticket['visitor_id']}"):
        return error("You're sending messages too fast. Please wait a moment.", 429)
    body, msg = parse(TicketMessageRequest, request.get_json(silent=True))
    if msg:
        return error(msg, 400)
    try:
        message_id = desk.customer_message(deps(), ticket, body.message)
    except desk.DeskError as e:
        return error(str(e), e.status)
    return jsonify(message_id=message_id)


@bp.post("/api/handoff/<int:ticket_id>/cancel")
def leave_queue(ticket_id):
    ticket, err = _own_ticket(ticket_id)
    if err:
        return err
    return jsonify(desk.public(deps(), desk.customer_leave(deps(), ticket)))
