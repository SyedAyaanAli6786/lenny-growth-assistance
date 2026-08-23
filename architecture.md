# architecture.md

## System overview

```
┌────────────┐     REST/JSON     ┌───────────────────┐
│  Frontend   │ ────────────────▶ │   FastAPI backend   │
│  (Vite/React)│ ◀──────────────── │                     │
└────────────┘                   │  ┌───────────────┐  │      ┌────────────┐
                                  │  │ orchestrator   │──┼─────▶│  Postgres   │
                                  │  │ (retrieve→gen) │  │      │  + pgvector │
                                  │  └──────┬────────┘  │      └────────────┘
                                  │         │            │
                                  │  ┌──────▼────────┐  │      ┌────────────┐
                                  │  │ provider router│──┼─────▶│   Ollama    │
                                  │  │ (config-driven)│  │      │  (chat +    │
                                  │  └──────┬────────┘  │      │   embed)    │
                                  │         │            │      └────────────┘
                                  │  ┌──────▼────────┐  │      ┌────────────┐
                                  │  │ Claude Agent   │──┼─────▶│  Anthropic  │
                                  │  │ SDK client      │  │      │  API        │
                                  │  └───────────────┘  │      └────────────┘
                                  └───────────────────┘
```

## Component boundaries

- **`backend/app/api/`** — FastAPI routers + Pydantic request/response contracts. No business logic; delegates to `agent/` and `rag/`.
- **`backend/app/agent/`** — provider-agnostic orchestration. `base.py` defines the `LLMProvider` interface (`generate(messages, system_prompt) -> ProviderResponse`); `anthropic_provider.py` and `ollama_provider.py` implement it; `orchestrator.py` wires retrieval + prompt construction + provider call + citation/artifact parsing; `skills/ship30.py` is a structured prompt template + validator, not an ad hoc string.
- **`backend/app/rag/`** — `chunking.py` (frontmatter parsing + overlap chunking), `embeddings.py` (Ollama embedding client), `retrieval.py` (pgvector top-k cosine query + relevance threshold).
- **`backend/app/artifacts/`** — `detect.py` parses fenced code blocks out of a model response into typed artifact objects.
- **`backend/app/db/`** — SQLAlchemy models + session management; Alembic migrations own schema changes.
- **`scripts/ingest.py`** — standalone CLI, not imported by the API process, so ingestion can be re-run/scheduled independently of the running server.

## Database schema (PostgreSQL + pgvector)

```sql
-- sessions: one per independent chat context
sessions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title         text,
  user_ref      text,            -- client-generated pseudo-user id, not an auth identity
  llm_provider  text NOT NULL DEFAULT 'ollama',
  llm_model     text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
)

-- messages: full turn history per session
messages (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id    uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role          text NOT NULL CHECK (role IN ('user','assistant','system')),
  content       text NOT NULL,
  provider      text,            -- which provider produced this specific message
  citations     jsonb,           -- [{source_id, title, guest, url, score}]
  created_at    timestamptz NOT NULL DEFAULT now()
)

-- artifacts: generated markdown/html, linked back to the message that produced them
artifacts (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id    uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  message_id    uuid REFERENCES messages(id) ON DELETE SET NULL,
  type          text NOT NULL CHECK (type IN ('markdown','html')),
  title         text,
  content       text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
)

-- transcript_sources: one row per ingested episode
transcript_sources (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug          text UNIQUE NOT NULL,
  title         text NOT NULL,
  guest         text,
  published_at  date,
  url           text,
  content_hash  text NOT NULL,   -- drives idempotent re-ingestion
  ingested_at   timestamptz NOT NULL DEFAULT now()
)

-- transcript_chunks: retrieval unit
transcript_chunks (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id     uuid NOT NULL REFERENCES transcript_sources(id) ON DELETE CASCADE,
  chunk_index   int NOT NULL,
  content       text NOT NULL,
  token_count   int NOT NULL,
  embedding     vector(768) NOT NULL,   -- dim matches OLLAMA_EMBED_MODEL
  UNIQUE (source_id, chunk_index)
)
```

`transcript_sources.content_hash` (sha256 of the raw file) lets `scripts/ingest.py` be re-run safely: unchanged files are skipped, changed files have their chunks replaced, matching the brief's "refreshed" ingestion requirement.

## API contract (summary)

| Method & path | Purpose |
|---|---|
| `POST /api/sessions` | Create a session; returns id, default provider/model. |
| `GET /api/sessions` | List sessions (id, title, updated_at) for the sidebar. |
| `GET /api/sessions/{id}` | Fetch a session with its full message history. |
| `POST /api/sessions/{id}/messages` | Send a user message; returns the assistant message, citations, and an artifact object if one was produced. |
| `POST /api/sessions/{id}/ship30` | Run the Ship 30 skill against the session's grounded context; returns a markdown artifact. |
| `PATCH /api/sessions/{id}/provider` | Switch the active provider/model for the next message in this session. |
| `GET /api/sources` | List ingested transcripts with chunk counts and ingested_at, for traceability. |
| `GET /health` | Component-level status: `db`, `ollama`, `anthropic_key_present`, each `ok`/`degraded`/`down`. |

All error responses share one shape: `{"error": {"code": "...", "message": "...", "component": "..."}}` with an appropriate HTTP status (400 validation, 404 not found, 503 dependency unavailable, 504 timeout) — never a bare 500 with a stack trace.

## Ingestion / retrieval flow

1. `scripts/ingest.py` reads `data/transcripts/*.md`, parses YAML frontmatter (guest, title, url, date) via `python-frontmatter`.
2. `rag/chunking.py` splits body text into ~600-token chunks with ~80-token overlap, preserving paragraph boundaries where possible.
3. `rag/embeddings.py` calls Ollama's `/api/embeddings` with `nomic-embed-text` for each chunk.
4. Chunks + embeddings upsert into `transcript_chunks`; the source's `content_hash` updates in `transcript_sources`.
5. At query time, `rag/retrieval.py` embeds the user's question the same way and runs a pgvector `<=>` cosine-distance top-k query, filtering out results below a similarity threshold (configurable, default tuned during testing).
6. `agent/orchestrator.py` builds a system prompt containing the retrieved chunks (with source ids) and citation-format instructions, then calls the currently configured provider.

## Agent routing / model toggle

- `Settings.LLM_PROVIDER` (`anthropic` | `ollama`) is the process-wide default, read once at startup from `.env` — satisfies "switch without changing application code" via a restart-only config change.
- A session can override that default at runtime via `PATCH /api/sessions/{id}/provider`, validated against `/health` (can't select a provider that's currently down) — this is what makes the live demo toggle possible without restarting anything.
- `agent/base.py` defines one `LLMProvider` interface both implementations satisfy, so `orchestrator.py` is provider-agnostic — it always does retrieval first, then calls `provider.generate(...)` with the same constructed prompt.
- **Anthropic path**: `agent/anthropic_provider.py` uses the Claude Agent SDK (`ClaudeSDKClient`) with a per-request system prompt and no filesystem/bash tools enabled — the SDK here is the execution/session layer, not a free-roaming coding agent.
- **Ollama path**: `agent/ollama_provider.py` is a thin `httpx` client against Ollama's `/api/chat`, given the identical system prompt and message history, so behavior stays consistent across the toggle.
- This split is a deliberate trade-off (see PRD Risks): the Agent SDK cannot itself target Ollama, so full architectural parity (one SDK for both) isn't possible under the brief's constraints — documented rather than hidden.

## Security: artifact rendering

Generated HTML is treated as fully untrusted input:

- Rendered client-side inside `<iframe srcdoc="...">`. Using `srcdoc` (rather than a same-origin route) gives the frame a unique opaque origin.
- `sandbox="allow-scripts"` only — **no** `allow-same-origin`, `allow-top-navigation`, `allow-forms`, or `allow-popups`. Scripts in the artifact can run (so demo visuals work), but cannot read/write the parent page, cannot navigate the top window, cannot submit forms, and — because the frame's origin is opaque/null — cannot use cookies, `localStorage`, or make same-origin fetches back to our app.
- An injected `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">` is prepended to every HTML artifact server-side before it's handed to the frontend, blocking outbound network calls (`fetch`, `XHR`, image/script loads to remote hosts) from inside the sandbox as defense in depth beyond the sandbox attribute alone.
- Markdown artifacts are rendered through a markdown renderer with raw HTML disabled (no `dangerouslySetInnerHTML` on unsanitized output) — markdown never gets an HTML escape hatch.
- The Artifact Viewer surfaces this policy to the user directly (see `design.md`), not just in engineering docs.

## Deployment topology

`docker-compose.yml` services:

- **`db`** — `pgvector/pgvector:pg16`, named volume, healthcheck-gated.
- **`ollama`** — official `ollama/ollama` image, named volume for model weights; an init step pulls `OLLAMA_MODEL` and `OLLAMA_EMBED_MODEL` on first boot.
- **`backend`** — FastAPI + Uvicorn, `depends_on: db (healthy)`; runs Alembic migrations on startup.
- **`frontend`** — Vite build served via a small static server (or Vite dev server for the evaluator's convenience); talks to `backend` over `VITE_API_BASE_URL`.

One command (`docker compose up --build`, or `make up`) starts everything; `scripts/ingest.py` is run once (via `make ingest`) to populate the knowledge base. Full details and troubleshooting live in `README.md`.
