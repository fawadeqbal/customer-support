"""
    GET  /api/health                         status, chunk count, active providers (public)

The admin panel (/admin in the website). Every route needs  Authorization: Bearer ADMIN_TOKEN
    GET  /api/admin/stats                    usage numbers + queue counts
    GET  /api/admin/tickets                  open tickets + the ones closed in the last 24 h
    GET  /api/admin/tickets/<id>?after=<id>  one ticket and its whole chat (bot answers included)
    POST /api/admin/tickets/<id>/claim       {agent}             take it ("Ali joined the chat")
    POST /api/admin/tickets/<id>/messages    {agent, message}    reply to the customer
    POST /api/admin/tickets/<id>/close       {agent}             finish; the assistant takes over again
    GET  /api/admin/files/<id>               download a file the customer attached
"""
import hmac
from functools import wraps

from flask import Blueprint, Response, jsonify, request

from app.api.common import deps, error
from app.api.schemas import AgentRequest, TicketMessageRequest, parse
from app.core import config
from app.support import desk

bp = Blueprint("admin", __name__)


@bp.get("/api/health")
def health():
    d = deps()
    try:
        d.conversations.questions_today()          # touches the database
        return jsonify(status="ok", chunks=d.knowledge.chunk_count, providers={
            "llm": d.assistant.chat.name, "fast_llm": d.assistant.fast.name,
            "embeddings": d.knowledge.embeddings.name, "reranker": d.knowledge.reranker.name,
            "vector_store": d.knowledge.store.name,
        })
    except Exception as e:
        return jsonify(status="error", detail=str(e)), 503


def admin_only(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not config.ADMIN_TOKEN or not hmac.compare_digest(token, config.ADMIN_TOKEN):
            return error("Not allowed.", 403)
        try:
            return view(*args, **kwargs)
        except desk.DeskError as e:
            return error(str(e), e.status)
    return wrapper


@bp.get("/api/admin/stats")
@admin_only
def admin_stats():
    queue = deps().tickets.counts()
    return jsonify({**deps().feedback.stats(), **queue, "daily_cap": config.DAILY_REQUEST_CAP,
                    "agents_on_shift": config.SUPPORT_AGENTS})


@bp.get("/api/admin/tickets")
@admin_only
def list_tickets():
    return jsonify([{**t, **desk.queue_info(deps(), t)} for t in deps().tickets.list()])


@bp.get("/api/admin/tickets/<int:ticket_id>")
@admin_only
def ticket_detail(ticket_id):
    ticket = deps().tickets.get(ticket_id)
    if ticket is None:
        return error("Ticket not found.", 404)
    after = request.args.get("after", 0, type=int)
    messages = deps().conversations.messages(ticket["conversation_id"], after=after) \
        if ticket.get("conversation_id") else []
    return jsonify({**ticket, **desk.queue_info(deps(), ticket), "messages": messages,
                    "files": deps().tickets.files(ticket_id)})


@bp.get("/api/admin/files/<int:file_id>")
@admin_only
def download_file(file_id):
    f = deps().tickets.get_file(file_id)
    if f is None:
        return error("File not found.", 404)
    safe_name = f["filename"].replace('"', "")
    return Response(bytes(f["data"]), mimetype=f["content_type"], headers={
        "Content-Disposition": f'inline; filename="{safe_name}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'",
    })


def _body(model):
    body, msg = parse(model, request.get_json(silent=True))
    if msg:
        raise desk.DeskError(msg, 400)
    return body


@bp.post("/api/admin/tickets/<int:ticket_id>/claim")
@admin_only
def claim_ticket(ticket_id):
    return jsonify(desk.claim(deps(), ticket_id, _body(AgentRequest).agent))


@bp.post("/api/admin/tickets/<int:ticket_id>/messages")
@admin_only
def reply(ticket_id):
    body = _body(TicketMessageRequest)
    agent = (body.agent or "").strip()[:40] or "Support"
    return jsonify(message_id=desk.agent_message(deps(), ticket_id, agent, body.message))


@bp.post("/api/admin/tickets/<int:ticket_id>/close")
@admin_only
def close_ticket(ticket_id):
    return jsonify(desk.close(deps(), ticket_id, _body(AgentRequest).agent))
