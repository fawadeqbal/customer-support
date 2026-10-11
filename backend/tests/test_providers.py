"""
The OpenAI-compatible adapter (Ollama, OpenAI, vLLM...) against a fake server that streams
like the real ones: text in pieces, tool calls split across chunks, usage at the end.
"""
import json
import threading

from flask import Flask, Response, request
from werkzeug.serving import make_server

from app.providers.embeddings import OpenAICompatibleEmbeddings
from app.providers.llm_openai_compat import OpenAICompatibleChat
from app.rag.generation import Assistant

TOOLS = [{"name": "lookup_order", "description": "d",
          "parameters": {"type": "object", "properties": {"order_number": {"type": "string"}}}}]


def _fake_server():
    app = Flask("fake-openai")

    def sse(obj):
        return f"data: {json.dumps(obj)}\n\n"

    @app.post("/v1/chat/completions")
    def completions():
        body = request.get_json()
        msgs = body["messages"]
        if not body.get("stream"):
            return {"choices": [{"message": {"role": "assistant", "content": "refund timeline"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 50, "completion_tokens": 3}}

        def gen():
            if body.get("tools") and not any(m.get("role") == "tool" for m in msgs) and "SE1" in msgs[-1]["content"]:
                yield sse({"choices": [{"index": 0, "delta": {"content": "Let me check. "}}]})
                yield sse({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                                                              "function": {"name": "lookup_order", "arguments": ""}}]}}]})
                yield sse({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\"order_"}}]}}]})
                yield sse({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "number\": \"SE10482931\"}"}}]}}]})
                yield sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]})
                yield sse({"choices": [], "usage": {"prompt_tokens": 400, "completion_tokens": 20}})
            else:
                for w in ["Your order ", "is **Shipped**. ", "ریفنڈ"]:
                    yield sse({"choices": [{"index": 0, "delta": {"content": w}}]})
                yield sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
                yield sse({"choices": [], "usage": {"prompt_tokens": 500, "completion_tokens": 15}})
            yield "data: [DONE]\n\n"
        return Response(gen(), mimetype="text/event-stream")

    @app.post("/v1/embeddings")
    def embeddings():
        return {"data": [{"index": i, "embedding": [3.0, 4.0] + [0.0] * 6} for i, _ in enumerate(request.get_json()["input"])]}

    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/v1"


def test_streaming_tool_calls_and_usage():
    server, url = _fake_server()
    try:
        chat = OpenAICompatibleChat("m", url, label="ollama")
        calls = []

        def run_tool(name, args):
            calls.append((name, args))
            return json.dumps({"status": "Shipped"})

        bot = Assistant(chat=chat, fast=chat, tools=TOOLS, run_tool=run_tool)
        events = list(bot.stream("Where is SE10482931?", ["context"], []))
        text = "".join(v for k, v in events if k == "delta")
        assert calls == [("lookup_order", {"order_number": "SE10482931"})]
        assert text.startswith("Let me check.") and "Shipped" in text and "ریفنڈ" in text
        assert dict(events)["usage"] == {"input": 900, "output": 35}
        assert bot.rewrite_query("ریفنڈ کب ملے گا", [])[0] == "refund timeline"
    finally:
        server.shutdown()


def test_model_without_tools_gets_order_prefetched():
    server, url = _fake_server()
    try:
        chat = OpenAICompatibleChat("m", url, supports_tools=False)
        bot = Assistant(chat=chat, fast=chat, tools=TOOLS, run_tool=lambda *a: "{}",
                        prefetch=lambda q: "Order lookup result: Shipped" if "SE1" in q else "")
        events = list(bot.stream("Where is SE10482931?", [], []))
        assert ("tool", "lookup_order") in events
    finally:
        server.shutdown()


def test_embeddings_are_normalised():
    server, url = _fake_server()
    try:
        emb = OpenAICompatibleEmbeddings("e", url)
        v = emb.embed_query("hi")
        assert abs(sum(x * x for x in v) - 1) < 1e-6 and len(emb.embed_documents(["a", "b"])) == 2
    finally:
        server.shutdown()
