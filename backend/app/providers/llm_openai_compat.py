"""
Any server that speaks the OpenAI Chat Completions API:
Ollama (local), OpenAI, vLLM, LM Studio, llama.cpp server, Groq, OpenRouter, Together...
Plain HTTP (requests), so no extra SDK is needed.
"""
import json

import requests

from app.providers.base import ToolCall, Turn


def _parse_args(value):
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


class OpenAICompatibleChat:
    def __init__(self, model, base_url, api_key="", supports_tools=True, timeout=300, label="openai_compatible"):
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.supports_tools = supports_tools
        self.timeout = timeout
        self.name = f"{label}:{model}"

    def _payload(self, system, messages, max_tokens, tools, stream):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if tools and self.supports_tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in tools]
        return payload

    def complete(self, system, messages, max_tokens):
        r = requests.post(self.url, json=self._payload(system, messages, max_tokens, None, False),
                          headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        return Turn(text=msg.get("content") or "", input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    stop_reason=data["choices"][0].get("finish_reason") or "", raw=msg)

    def stream(self, system, messages, max_tokens, tools=None):
        text, calls, usage, finish = [], {}, {}, ""
        with requests.post(self.url, json=self._payload(system, messages, max_tokens, tools, True),
                           headers=self.headers, stream=True, timeout=self.timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        text.append(delta["content"])
                        yield "text", delta["content"]
                    for tc in delta.get("tool_calls") or []:   # tool calls arrive in pieces
                        slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                        slot["id"] = tc.get("id") or slot["id"]
                        fn = tc.get("function") or {}
                        slot["name"] = slot["name"] or fn.get("name") or ""
                        args = fn.get("arguments")
                        slot["args"] += json.dumps(args) if isinstance(args, dict) else (args or "")
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]

        tool_calls = [ToolCall(s["id"] or f"call_{i}", s["name"], _parse_args(s["args"]))
                      for i, s in sorted(calls.items())]
        raw = {"role": "assistant", "content": "".join(text) or None}
        if tool_calls:
            raw["tool_calls"] = [{"id": c.id, "type": "function",
                                  "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                                 for c in tool_calls]
        yield "turn", Turn(text="".join(text), tool_calls=tool_calls,
                           input_tokens=usage.get("prompt_tokens", 0), output_tokens=usage.get("completion_tokens", 0),
                           stop_reason=finish, raw=raw)

    def add_tool_results(self, messages, turn, results):
        return messages + [turn.raw] + [
            {"role": "tool", "tool_call_id": call.id, "content": result} for call, result in results
        ]
