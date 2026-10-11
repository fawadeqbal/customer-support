"""Claude through the Anthropic SDK."""
import anthropic

from app.providers.base import ToolCall, Turn


class AnthropicChat:
    supports_tools = True

    def __init__(self, model, api_key=""):
        self.client = anthropic.Anthropic(api_key=api_key or None)   # falls back to ANTHROPIC_API_KEY
        self.model = model
        self.name = f"anthropic:{model}"

    @staticmethod
    def _tools(tools):
        return [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]

    @staticmethod
    def _turn(message):
        return Turn(
            text="".join(b.text for b in message.content if b.type == "text"),
            tool_calls=[ToolCall(b.id, b.name, dict(b.input)) for b in message.content if b.type == "tool_use"],
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=message.stop_reason or "",
            raw=message.content,
        )

    def complete(self, system, messages, max_tokens):
        return self._turn(self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=messages))

    def stream(self, system, messages, max_tokens, tools=None):
        kwargs = dict(model=self.model, max_tokens=max_tokens, system=system, messages=messages)
        if tools:
            kwargs["tools"] = self._tools(tools)
        with self.client.messages.stream(**kwargs) as s:
            for text in s.text_stream:
                yield "text", text
            final = s.get_final_message()
        yield "turn", self._turn(final)

    def add_tool_results(self, messages, turn, results):
        return messages + [
            {"role": "assistant", "content": turn.raw},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": call.id, "content": result} for call, result in results
            ]},
        ]
