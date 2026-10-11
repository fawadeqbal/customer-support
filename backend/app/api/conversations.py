"""
The visitor's chats.

    GET    /api/conversations                   list (sidebar)
    GET    /api/conversations/<id>/messages     open one
    DELETE /api/conversations/<id>              delete one (and its messages)
"""
from flask import Blueprint, jsonify

from app.api.common import deps, error, visitor_id

bp = Blueprint("conversations", __name__)


@bp.get("/api/conversations")
def list_conversations():
    vid = visitor_id()
    if not vid:
        return jsonify([])
    return jsonify([{k: c[k] for k in ("id", "title", "updated_at")} for c in deps().conversations.list(vid)])


@bp.get("/api/conversations/<conversation_id>/messages")
def get_messages(conversation_id):
    repo = deps().conversations
    if not repo.get(conversation_id, visitor_id()):
        return error("Chat not found.", 404)
    return jsonify(repo.messages(conversation_id))


@bp.delete("/api/conversations/<conversation_id>")
def delete_conversation(conversation_id):
    vid, repo = visitor_id(), deps().conversations
    if not repo.get(conversation_id, vid):
        return error("Chat not found.", 404)
    repo.delete(conversation_id, vid)
    return jsonify(deleted=conversation_id)
