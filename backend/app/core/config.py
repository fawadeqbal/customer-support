"""
app/core/config.py - SETTINGS
Everything you might want to change lives here. Prompts live in app/prompts/*.md.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]   # the backend/ folder
load_dotenv(BASE_DIR / ".env")  # loads ANTHROPIC_API_KEY, DATABASE_URL and ADMIN_TOKEN

# ---- database ----
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rag:rag@localhost:5432/rag")

# ---- documents + chunking ----
DATA_DIR = BASE_DIR / "data"            # put your PDF files here
EVAL_FILE = BASE_DIR / "eval" / "questions.json"
CHUNK_SIZE = 800       # max characters per chunk (most handbook sections fit in one)
CHUNK_OVERLAP = 100    # characters shared when a long section must be split

# ---- models: every part is replaceable --------------------------------------------
# Each setting can be overridden with an environment variable of the same name
# (e.g. in .env or .env.prod), so you can switch without touching code.
# See docs/PROVIDERS.md for ready-made combinations (Claude, Ollama, OpenAI, ...).
env = os.getenv

# Main model: writes the answers.   provider: ollama | anthropic | openai | openai_compatible
# Default: fully local with Ollama (started by docker compose). For Claude: LLM_PROVIDER=anthropic.
_provider = env("LLM_PROVIDER", "ollama")
LLM = {
    "provider": _provider,
    "model": env("LLM_MODEL", "qwen2.5:3b" if _provider == "ollama" else "claude-haiku-5-5"),
    "base_url": env("LLM_BASE_URL", ""),            # Ollama default: http://localhost:11434/v1
    "api_key": env("LLM_API_KEY", ""),              # Claude falls back to ANTHROPIC_API_KEY
    # Small local models call tools unreliably, so by default order numbers are looked up for them
    "supports_tools": env("LLM_SUPPORTS_TOOLS", "false" if _provider == "ollama" else "true").lower() == "true",
}
# Fast model: query rewriting + chat summaries. Same as the main model unless set.
FAST_LLM = {
    "provider": env("FAST_LLM_PROVIDER", LLM["provider"]),
    "model": env("FAST_LLM_MODEL", LLM["model"]),
    "base_url": env("FAST_LLM_BASE_URL", LLM["base_url"]),
    "api_key": env("FAST_LLM_API_KEY", LLM["api_key"]),
    "supports_tools": False,
}

# Embeddings: text -> vectors.   provider: sentence_transformers | ollama | openai | openai_compatible
# Changing the model? Set EMBEDDING_DIM to its size and run  python -m scripts.ingest  again.
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER", "sentence_transformers")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDING_DIM = int(env("EMBEDDING_DIM", "384"))
EMBEDDING_BASE_URL = env("EMBEDDING_BASE_URL", "")
EMBEDDING_API_KEY = env("EMBEDDING_API_KEY", "")

# Reranker: re-scores the best candidates.   provider: cross_encoder | none
RERANKER_PROVIDER = env("RERANKER_PROVIDER", "cross_encoder")
RERANK_MODEL = env("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# Vector store: where chunks live and how they are searched.   pgvector
VECTOR_STORE = env("VECTOR_STORE", "pgvector")

# ---- retrieval ----
CANDIDATES = 20        # how many chunks vector search and keyword search each bring back
TOP_K = 4              # at most this many chunks go to Claude
MIN_SCORE = 0.3        # drop chunks less similar than this (tune with: python -m scripts.evaluate --sweep)
REWRITE_QUERIES = True # turn follow-ups / non-English questions into standalone English search queries

# ---- memory + token savers ----
MEMORY_TURNS = 4           # last question/answer pairs sent word for word
HISTORY_CHAR_LIMIT = 600   # old answers are cut to this many characters
MAX_ANSWER_TOKENS = 1500   # safety cap, not the target length: Claude may think before it writes,
                           # and Urdu uses 3-4x more tokens. The prompt keeps answers short.
# Older messages are folded into a short running summary (see app/graph/nodes/memory.py)

# ---- protection for a public demo ----
MAX_QUESTION_CHARS = 1000
RATE_LIMIT_PER_MINUTE = 8      # per visitor (one browser)
IP_RATE_LIMIT_PER_MINUTE = 30  # per IP address (offices and campuses share one IP)
DAILY_REQUEST_CAP = 400        # questions per day for the whole site (protects the API bill)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")   # for the admin panel (/admin) and /api/admin/*

# ---- human support queue ----
SUPPORT_AGENTS = int(os.getenv("SUPPORT_AGENTS", "2"))           # agents on shift, each takes one chat at a time
AVG_HANDLE_MINUTES = float(os.getenv("AVG_HANDLE_MINUTES", "5"))  # wait estimate until real tickets give an average
TICKET_MAX_FILES = 3
TICKET_MAX_FILE_MB = 5
TICKET_FILE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
                     ".gif": "image/gif", ".pdf": "application/pdf", ".txt": "text/plain"}
