"""
Chat in the terminal, running the same LangGraph workflow as the API.

    python -m scripts.chat

Each step of the graph is printed as it runs.
"""
from app.core.container import build_deps
from app.core.logging import setup_logging
from app.graph.graph import build_graph


def main():
    setup_logging()
    deps = build_deps()
    workflow = build_graph(deps)
    conversation = None

    print("\nShopEase Support Bot ready. ('reset' = new chat, 'quit' = exit)")
    print("Try: 'where is my order SE10482931?' or 'refund kitne din mein milta hai?'\n")
    while True:
        question = input("You: ").strip()
        if question.lower() in ("quit", "exit", ""):
            break
        if question.lower() == "reset":
            conversation = None
            print("\n(New chat started)\n")
            continue
        if conversation is None:
            conversation = {"id": None, "title": question[:60], "summary": "", "visitor_id": None}

        print()
        for chunk in workflow.stream({"question": question, "conversation": conversation}, stream_mode="custom"):
            event, data = chunk["event"], chunk["data"]
            if event == "step":
                print(f"  [{data['name']}]" + (f" route={data['route']}" if "route" in data else ""))
            elif event == "meta":
                print(f"  [search] {data['query']}")
                for r in data["sources"]:
                    print(f"    ({r['score']:.2f}) p.{r['page']} {r['title']}")
                print("\nAssistant: ", end="", flush=True)
            elif event == "tool":
                print(f"\n  [tool] {data['name']}", flush=True)
            elif event == "delta":
                print(data["text"], end="", flush=True)
            elif event == "done":
                u = data["usage"]
                saved = deps.conversations.get(data["conversation_id"], None) or {}
                conversation = {"id": data["conversation_id"], "title": data["title"],
                                "summary": saved.get("summary", ""), "visitor_id": None}
                print(f"\n\n  [tokens] {u['input']} in, {u['output']} out | {u['total_ms']} ms | route {u['route']}\n")


if __name__ == "__main__":
    main()
