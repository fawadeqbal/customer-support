"""
The chat workflow as a LangGraph graph: which nodes exist and how they connect.

  START -> load_memory -> classify --+-- handoff ----------------------------------+
                                     +-- generate (greeting) ----------------------+
                                     +-- rewrite -> retrieve --+-- generate -------+-> save -> END
                                                       ^       +-- broaden (nothing found)
                                                       +-----------+  (one retry, wider search)

Nodes live in app/graph/nodes/, decisions in app/graph/edges.py, the state in state.py.

    python -m app.graph.graph      prints the graph as a Mermaid diagram
"""
from langgraph.graph import END, START, StateGraph

from app.graph import edges
from app.graph.nodes.generation import generate
from app.graph.nodes.handoff import handoff
from app.graph.nodes.memory import load_memory, save
from app.graph.nodes.retrieval import broaden, retrieve, rewrite
from app.graph.nodes.router import classify
from app.graph.state import ChatState

NODES = {
    "load_memory": load_memory,
    "classify": classify,
    "rewrite": rewrite,
    "retrieve": retrieve,
    "broaden": broaden,
    "generate": generate,
    "handoff": handoff,
    "save": save,
}


def build_graph(deps):
    """deps: app.graph.deps.Deps (knowledge, assistant, conversations, feedback)."""
    g = StateGraph(ChatState)
    for name, node in NODES.items():
        g.add_node(name, lambda state, node=node: node(state, deps))

    g.add_edge(START, "load_memory")
    g.add_edge("load_memory", "classify")
    g.add_conditional_edges("classify", edges.after_classify, ["handoff", "generate", "rewrite"])
    g.add_edge("rewrite", "retrieve")
    g.add_conditional_edges("retrieve", edges.after_retrieve, ["generate", "broaden"])
    g.add_edge("broaden", "retrieve")
    g.add_edge("generate", "save")
    g.add_edge("handoff", "save")
    g.add_edge("save", END)
    return g.compile()


if __name__ == "__main__":
    # Draw the graph without loading any models or databases
    print(build_graph(deps=None).get_graph().draw_mermaid())
