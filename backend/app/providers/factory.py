"""
providers/factory.py - PICKS THE IMPLEMENTATION FOR EACH PART FROM app/core/config.py

    build_llm("main")       the model that writes answers
    build_llm("fast")       the model for small jobs (query rewriting, summaries)
    build_embeddings()      text -> vectors
    build_reranker()        re-scores passages
    build_vector_store()    where chunks live and how they are searched

Imports happen inside the functions, so you only need the libraries of the
providers you actually use (e.g. no 'anthropic' package for a fully local setup).

To add a provider: add a branch below (or a new file in providers/) and a name for config.py.
"""
from app.core import config

DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "openai": "https://api.openai.com/v1",
}
OPENAI_STYLE = ("openai_compatible", "ollama", "openai")


def build_llm(role="main"):
    settings = config.LLM if role == "main" else config.FAST_LLM
    provider = settings["provider"]
    if provider == "anthropic":
        from app.providers.llm_anthropic import AnthropicChat
        return AnthropicChat(settings["model"], settings.get("api_key", ""))
    if provider in OPENAI_STYLE:
        from app.providers.llm_openai_compat import OpenAICompatibleChat
        base_url = settings.get("base_url") or DEFAULT_BASE_URLS.get(provider)
        if not base_url:
            raise ValueError(f"Set a base URL for the {role} LLM ({provider}).")
        return OpenAICompatibleChat(settings["model"], base_url, settings.get("api_key", ""),
                                    supports_tools=settings.get("supports_tools", True), label=provider)
    raise ValueError(f"Unknown LLM provider '{provider}'. Use: anthropic, {', '.join(OPENAI_STYLE)}")


def build_embeddings():
    provider = config.EMBEDDING_PROVIDER
    if provider == "sentence_transformers":
        from app.providers.embeddings import SentenceTransformerEmbeddings
        return SentenceTransformerEmbeddings(config.EMBEDDING_MODEL)
    if provider in OPENAI_STYLE:
        from app.providers.embeddings import OpenAICompatibleEmbeddings
        base_url = config.EMBEDDING_BASE_URL or DEFAULT_BASE_URLS.get(provider)
        if not base_url:
            raise ValueError(f"Set EMBEDDING_BASE_URL for the {provider} embeddings.")
        return OpenAICompatibleEmbeddings(config.EMBEDDING_MODEL, base_url, config.EMBEDDING_API_KEY, label=provider)
    raise ValueError(f"Unknown embedding provider '{provider}'. Use: sentence_transformers, {', '.join(OPENAI_STYLE)}")


def build_reranker():
    provider = config.RERANKER_PROVIDER
    if provider == "cross_encoder":
        from app.providers.rerankers import CrossEncoderReranker
        return CrossEncoderReranker(config.RERANK_MODEL)
    if provider in ("none", "", None):
        from app.providers.rerankers import NoReranker
        return NoReranker()
    raise ValueError(f"Unknown reranker '{provider}'. Use: cross_encoder, none")


def build_vector_store():
    if config.VECTOR_STORE == "pgvector":
        from app.stores.pgvector import PgVectorStore
        return PgVectorStore()
    raise ValueError(f"Unknown vector store '{config.VECTOR_STORE}'. Use: pgvector")
