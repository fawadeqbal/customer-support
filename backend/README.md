# ShopEase support bot: backend

Flask API + LangGraph workflow + RAG (LangChain, PostgreSQL + pgvector).
Every model and store is replaceable from settings: Claude, Ollama, OpenAI, ... see [docs/PROVIDERS.md](docs/PROVIDERS.md).

## Layout

```
backend/
├── app/
│   ├── main.py                 Flask app factory: create_app()
│   ├── core/                   config.py (settings) · container.py (builds the real parts) · logging.py · security.py
│   ├── api/                    HTTP only: parse request -> run graph / repository -> respond
│   │   ├── chat.py             POST /api/chat, /api/chat/stream
│   │   ├── conversations.py    list / open / delete chats
│   │   ├── feedback.py         feedback + "talk to a person"
│   │   ├── admin.py            health + stats
│   │   ├── schemas.py          request validation (Pydantic)
│   │   └── common.py           shared helpers
│   ├── graph/                  the LangGraph workflow (docs/WORKFLOW.md)
│   │   ├── state.py · deps.py · events.py · edges.py · graph.py · studio.py
│   │   └── nodes/              memory · router · retrieval · generation · handoff
│   ├── prompts/                system.md · rewrite_query.md · summarize.md · handoff_reply.md
│   ├── tools/                  registry.py (all tools) · orders.py (lookup_order)
│   ├── rag/
│   │   ├── ingestion/          loaders (PDF, tables, OCR) · cleaning · chunking · pipeline
│   │   ├── retrieval.py        embed -> hybrid search -> filter -> rerank
│   │   └── generation.py       query rewriting, streamed answers with tools, summaries
│   ├── providers/              replaceable models: base interfaces, factory, Claude, OpenAI-compatible, embeddings, rerankers
│   ├── stores/pgvector.py      the knowledge-base table + hybrid search
│   └── db/
│       ├── connection.py · migrate.py
│       ├── migrations/         001_initial.sql · 002_demo_orders.sql
│       └── repositories/       conversations · feedback · orders  (all SQL lives here)
├── scripts/                    ingest · evaluate · chat · migrate
├── tests/                      pytest: chunking, graph routes, API contract, providers
├── data/ · eval/ · docs/
├── langgraph.json              LangGraph Studio
├── pyproject.toml · requirements.txt · requirements-dev.txt
└── Dockerfile · .env
```

## Run locally

Start the database (and, for local models, Ollama) from the project root:
`docker compose up -d` (or `docker compose --profile ollama up -d`). Then, from this `backend` folder:

```bash
pip install -r requirements-dev.txt
pytest                               # 25 tests, no database or API key needed
python -m scripts.ingest --preview   # look at the chunks
python -m scripts.ingest             # build the knowledge base (re-run when documents change)
python -m scripts.evaluate --sweep   # how well does retrieval work?
python -m app.main                   # API on http://localhost:5000
python -m scripts.chat               # or chat in the terminal
python -m app.graph.graph            # print the workflow graph
```

Database migrations run automatically on startup (`python -m scripts.migrate` to run them by hand).

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status, number of chunks, active providers |
| GET | `/api/conversations` | This visitor's chats |
| GET | `/api/conversations/<id>/messages` | Messages of one chat |
| DELETE | `/api/conversations/<id>` | Delete a chat |
| POST | `/api/chat/stream` | Ask a question; answer streams back (SSE: step, meta, tool, delta, done) |
| POST | `/api/chat` | Same, whole answer at once |
| POST | `/api/messages/<id>/feedback` | `{"value": "up" \| "down" \| null}` |
| POST | `/api/handoff` | "Talk to a person" ticket |
| GET | `/api/admin/stats` | Usage numbers (`Authorization: Bearer ADMIN_TOKEN`) |

Every request sends `X-Visitor-Id` (a random id the browser keeps), so visitors only see their own chats.
