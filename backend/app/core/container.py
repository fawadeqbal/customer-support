"""
Builds the real application parts once: database migrations, knowledge base,
model assistant and repositories. Used by the API, the scripts and LangGraph Studio.
Tests build a Deps with fakes instead.
"""
import logging

log = logging.getLogger(__name__)


def build_deps():
    from app.db.migrate import run_migrations
    from app.db.repositories.conversations import ConversationRepository
    from app.db.repositories.feedback import FeedbackRepository
    from app.db.repositories.tickets import TicketRepository
    from app.graph.deps import Deps
    from app.rag.generation import Assistant
    from app.rag.retrieval import KnowledgeBase
    from app.tools.registry import TOOLS, prefetch, run_tool

    run_migrations()
    deps = Deps(
        knowledge=KnowledgeBase(),
        assistant=Assistant(tools=TOOLS, run_tool=run_tool, prefetch=prefetch),
        conversations=ConversationRepository(),
        feedback=FeedbackRepository(),
        tickets=TicketRepository(),
    )
    log.info("models: llm=%s fast=%s", deps.assistant.chat.name, deps.assistant.fast.name)
    return deps
