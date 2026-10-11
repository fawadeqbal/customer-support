"""Small helpers shared by the route modules."""
from flask import current_app, jsonify, request

from app.core import config
from app.core.security import is_valid_id


def deps():
    return current_app.extensions["deps"]


def graph():
    return current_app.extensions["graph"]


def limiters():
    return current_app.extensions["limiters"]


def error(message, status, **extra):
    return jsonify(error=message, **extra), status


def visitor_id():
    vid = request.headers.get("X-Visitor-Id", "")
    return vid if is_valid_id(vid) else None


def client_ip():
    return request.headers.get("X-Real-IP") or request.remote_addr or "unknown"


def check_limits(vid):
    """An error response if this visitor/IP is sending too much, else None."""
    per_ip, per_visitor = limiters()
    for limiter, key in ((per_ip, f"ip:{client_ip()}"), (per_visitor, f"visitor:{vid}")):
        wait = limiter.retry_after(key)
        if wait:
            return error(f"You're sending messages too fast. Please wait {wait} seconds.", 429, retry_after=wait)
    if deps().conversations.questions_today() >= config.DAILY_REQUEST_CAP:
        return error("The demo has reached its daily limit. Please come back tomorrow.", 503)
    return None
