"""
providers/base.py - THE CONTRACTS every replaceable part must follow

The rest of the app only talks to these interfaces, never to a vendor SDK.
To add a new provider: write a class with these methods, register it in
providers/factory.py, and pick it in app/core/config.py (or with an environment variable).

    ChatModel     a chat LLM (Claude, Ollama, OpenAI, vLLM, ...)
    Embeddings    text -> vector
    Reranker      re-scores (question, passage) pairs
    VectorStore   stores chunks + vectors, does the search

Tools use one neutral format, converted by each ChatModel:
    {"name": "...", "description": "...", "parameters": {JSON schema}}

Chat messages use the plain format [{"role": "user"|"assistant", "content": "text"}].
During a tool round the provider may append its own message shapes (add_tool_results);
those lists are only ever passed back to the same provider.
"""
from dataclasses import dataclass, field
from typing import Iterator, Optional, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Turn:
    """One model reply."""
    text: str = ""
    tool_calls: list = field(default_factory=list)   # [ToolCall]
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    raw: object = None   # provider's own assistant message, needed for add_tool_results


class ChatModel(Protocol):
    name: str              # e.g. "anthropic:claude-haiku-5-5"
    supports_tools: bool

    def complete(self, system: str, messages: list, max_tokens: int) -> Turn:
        """Whole reply at once (no tools). Used for query rewriting and summaries."""

    def stream(self, system: str, messages: list, max_tokens: int, tools: Optional[list] = None) -> Iterator[tuple]:
        """Yields ("text", str) pieces as they arrive, then one final ("turn", Turn)."""

    def add_tool_results(self, messages: list, turn: Turn, results: list) -> list:
        """results = [(ToolCall, result_string)]. Returns the message list to send next."""


class Embeddings(Protocol):
    name: str

    def embed_documents(self, texts: list) -> list: ...
    def embed_query(self, text: str) -> list: ...


class Reranker(Protocol):
    name: str

    def score(self, query: str, passages: list) -> Optional[list]:
        """Higher = more relevant. None means 'keep the current order'."""


class VectorStore(Protocol):
    name: str

    def count(self) -> int: ...
    def dimension_ok(self) -> bool: ...
    def search(self, query_vector: list, query_text: str, candidates: int) -> list:
        """[{"title", "content", "source", "page", "similarity", "keyword_rank"}], best first."""
    def replace_all(self, chunks: list, vectors: list) -> int:
        """Replace the whole knowledge base. Returns the number of chunks stored."""
