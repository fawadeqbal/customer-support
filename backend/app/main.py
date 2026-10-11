"""
The Flask application (app factory).

    python -m app.main                       development server, http://localhost:5000
    gunicorn "app.main:create_app()"         production (see Dockerfile)

Routes live in app/api/, the chat workflow in app/graph/, data access in app/db/.
"""
from flask import Flask

from app.api import admin, chat, conversations, feedback, live, support
from app.core import config
from app.core.logging import setup_logging
from app.core.security import RateLimiter


def create_app(deps=None):
    """deps: app.graph.deps.Deps. Built from real models/database when not given (tests pass fakes)."""
    setup_logging()
    if deps is None:
        from app.core.container import build_deps
        deps = build_deps()
    from app.graph.graph import build_graph

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = (config.TICKET_MAX_FILES * config.TICKET_MAX_FILE_MB + 1) * 1024 * 1024
    app.extensions["deps"] = deps
    app.extensions["graph"] = build_graph(deps)
    app.extensions["limiters"] = (RateLimiter(config.IP_RATE_LIMIT_PER_MINUTE),   # per IP
                                  RateLimiter(config.RATE_LIMIT_PER_MINUTE))      # per visitor
    for module in (chat, conversations, feedback, support, admin):
        app.register_blueprint(module.bp)
    live.sock.init_app(app)          # WebSockets: /ws/support and /ws/admin
    return app


if __name__ == "__main__":
    # threaded=True so a streaming answer doesn't block other visitors
    create_app().run(host="127.0.0.1", port=5000, debug=False, threaded=True)
