"""
Entry point for LangGraph Studio (see backend/langgraph.json).

    pip install "langgraph-cli[inmem]"
    langgraph dev            # opens Studio: watch each node run and inspect the state

Input to try: {"question": "How do I return earbuds?",
               "conversation": {"id": null, "title": "Studio test", "summary": "", "visitor_id": null}}
"""
from app.core.container import build_deps
from app.graph.graph import build_graph

graph = build_graph(build_deps())
