"""
Every tool the model may call, in one place.

To add a tool: write a module like tools/orders.py with SPEC (name, description,
JSON-schema parameters), run(arguments) and optionally prefetch(question), then add it below.
"""
import json

from app.tools import orders, support

_TOOLS = [orders, support]

TOOLS = [t.SPEC for t in _TOOLS]                 # given to the model
_BY_NAME = {t.SPEC["name"]: t for t in _TOOLS}


def run_tool(name, arguments):
    """Called when the model asks for a tool. Returns a JSON string."""
    tool = _BY_NAME.get(name)
    result = tool.run(arguments) if tool else {"error": f"Unknown tool {name}"}
    return json.dumps(result, default=str)


def prefetch(question):
    """Extra context for models that can't call tools themselves."""
    return "\n".join(p for t in _TOOLS if hasattr(t, "prefetch") and (p := t.prefetch(question)))
