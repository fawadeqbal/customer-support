# Swapping models and parts

Every replaceable part sits behind a small interface (`app/providers/base.py`).
`app/providers/factory.py` picks the implementation from settings in `app/core/config.py`,
and **every setting can be overridden with an environment variable** (in `.env` locally,
`.env.prod` on the server). Nothing else in the code changes when you swap a part.

| Part | Setting | Options |
|---|---|---|
| Main model (answers) | `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_SUPPORTS_TOOLS` | `anthropic`, `ollama`, `openai`, `openai_compatible` |
| Fast model (rewriting, summaries) | `FAST_LLM_PROVIDER`, `FAST_LLM_MODEL`, `FAST_LLM_BASE_URL`, `FAST_LLM_API_KEY` | same as above; defaults to the main model |
| Embeddings | `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `EMBEDDING_BASE_URL` | `sentence_transformers`, `ollama`, `openai`, `openai_compatible` |
| Reranker | `RERANKER_PROVIDER`, `RERANK_MODEL` | `cross_encoder`, `none` |
| Vector store | `VECTOR_STORE` | `pgvector` |

`openai_compatible` covers any server with the OpenAI Chat Completions API:
Ollama, vLLM, LM Studio, llama.cpp server, Groq, OpenRouter, Together and others.

Check what is running: `GET /api/health` lists the active providers.

## Ready-made combinations (put these in `.env`)

**Default: fully local and free** (nothing to set)
```
LLM_PROVIDER=ollama             # the rag-ollama container started by docker compose
LLM_MODEL=qwen2.5:3b            # downloaded automatically by the ollama-pull job
LLM_SUPPORTS_TOOLS=false        # small models call tools unreliably; order numbers are looked up for them
```
Embeddings (`paraphrase-multilingual-MiniLM-L12-v2`) and the reranker run inside the API itself.
Smaller/faster: `qwen2.5:1.5b`. Better answers (needs more RAM/CPU or a GPU): `qwen2.5:7b`, `llama3.1:8b`.
Change the model in both places: `LLM_MODEL=... docker compose up -d` and `LLM_MODEL=...` in `.env`.

**Claude for answers** (best quality, pay per token)
```
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-5-5
ANTHROPIC_API_KEY=sk-ant-...
```

**Hybrid: local model for small jobs, Claude for answers** (cheaper)
```
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-5-5
FAST_LLM_PROVIDER=ollama
FAST_LLM_MODEL=qwen2.5:1.5b
```

**OpenAI**
```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...
```

**Any other OpenAI-compatible server** (vLLM, LM Studio, Groq, OpenRouter...)
```
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=your-model-name
LLM_API_KEY=...                 # if the server needs one
```

**Embeddings from Ollama instead of the built-in model**
```
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```
Changing embeddings always means re-running `python -m scripts.ingest`: vectors from
different models can't be mixed. The chunks table is rebuilt automatically for the new size,
and the API refuses to start until you do (instead of returning wrong results).

## On the server (Docker)

`docker-compose.prod.yml` runs Ollama as the `rag-ollama` container on the private network
(never exposed to the internet), and `rag-ollama-pull` downloads `LLM_MODEL` on each deploy
if it isn't there yet. Put your settings in `~/RAG/.env.prod` and run `bash deploy.sh`.
On the 2-core server, `qwen2.5:1.5b` answers roughly twice as fast as `qwen2.5:3b`.

## Adding a new provider

1. Write a class with the methods from `app/providers/base.py`
   (e.g. `ChatModel`: `complete`, `stream`, `add_tool_results`, plus `name` and `supports_tools`).
2. Add a branch for it in `app/providers/factory.py`.
3. Select it with the matching setting.

The workflow, API, memory and frontend never change.
