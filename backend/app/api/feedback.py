"""
    POST /api/messages/<id>/feedback   {"value": "up" | "down" | null}
"""
from flask import Blueprint, jsonify, request

from app.api.common import deps, error, visitor_id
from app.api.schemas import FeedbackRequest, parse

bp = Blueprint("feedback", __name__)


@bp.post("/api/messages/<int:message_id>/feedback")
def feedback(message_id):
    vid = visitor_id()
    body, msg = parse(FeedbackRequest, request.get_json(silent=True))
    if msg:
        return error(msg, 400)
    if not vid or not deps().feedback.set_feedback(message_id, vid, body.value):
        return error("Message not found.", 404)
    return jsonify(saved=True)

