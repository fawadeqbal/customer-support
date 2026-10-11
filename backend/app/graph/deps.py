"""
What the nodes need from the outside world, passed in once when the graph is built.
Tests pass fakes here, so every node can be tested without models or a database.
"""
from dataclasses import dataclass


@dataclass
class Deps:
    knowledge: object       # app.rag.retrieval.KnowledgeBase      search(question, ...), chunk_count
    assistant: object       # app.rag.generation.Assistant         rewrite_query, stream, summarize
    conversations: object   # app.db.repositories.conversations    history, create, add_message, ...
    feedback: object        # app.db.repositories.feedback         set_feedback, stats
    tickets: object         # app.db.repositories.tickets          the human support queue
