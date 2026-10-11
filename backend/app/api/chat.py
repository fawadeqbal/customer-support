"""
Asking questions. Both routes run the LangGraph workflow (app/graph/graph.py).

    POST /api/chat/stream   answer streams back as Server-Sent Events (step, meta, tool, delta, done)
    POST /api/chat          the whole answer at once
"""
import json
import logging

from flask import Blueprint, Response, jsonify, request

from app.api.common import check_limits, deps, error, graph, visitor_id
from app.api.schemas import ChatRequest, parse

log = logging.getLogger(__name__)
bp = Blueprint("chat", __name__)


def _start():
    """Validate and find (or prepare) the conversation. Returns (inputs, error_response)."""
    vid = visitor_id()
    if not vid:
        return None, error("Missing visitor id.", 400)
    body, msg = parse(ChatRequest, request.get_json(silent=True))
    if msg:
        return None, error(msg, 400)
    limited = check_limits(vid)
    if limited:
        return None, limited
    if body.conversation_id:
        conversation = deps().conversations.get(body.conversation_id, vid)
        if conversation is None:
            return None, error("Chat not found.", 404)
        ticket = deps().tickets.open_for(conversation["id"])
        if ticket:   # a person is (about to be) handling this chat, so the assistant stays quiet
            return None, error("You're connected to our support team. Your message goes to the agent.", 409,
                               ticket=ticket["id"])
    else:   # new chat: created only once there is an answer (save node)
        conversation = {"id": None, "title": body.message[:60], "summary": ""}
    conversation["visitor_id"] = vid
    return {"question": body.message, "conversation": conversation}, None


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@bp.post("/api/chat/stream")
def chat_stream():
    inputs, err = _start()
    if err:
        return err
    workflow = graph()

    def events():
        try:
            for chunk in workflow.stream(inputs, stream_mode="custom"):
                yield _sse(chunk["event"], chunk["data"])
        except Exception:
            log.exception("chat stream failed")
            yield _sse("error", {"error": "The assistant failed to answer. Please try again."})

    return Response(events(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.post("/api/chat")
def chat():
    inputs, err = _start()
    if err:
        return err
    try:
        final = graph().invoke(inputs)
    except Exception:
        log.exception("chat failed")
        return error("The assistant failed to answer. Check the API logs.", 500)
    conv = final["conversation"]
    return jsonify(conversation_id=conv["id"], title=conv["title"], message_id=final["message_id"],
                   answer=final["answer"], sources=final["results"], usage=final["usage"],
                   chunks_searched=deps().knowledge.chunk_count)
