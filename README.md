# The Lenny Growth Assistant

A grounded RAG chat app over Lenny's Podcast/Newsletter transcripts, with a cloud (Claude)/local (Ollama) model toggle, a structured Ship 30 for 30 essay skill, and an in-app sandboxed artifact viewer. Built for the Forward Deployed Engineer take-home — see `PRD.md`, `design.md`, and `architecture.md` for the discovery brief, UX rationale, and technical design in full.

## Architecture overview

```
Frontend (React/Vite) ──▶ FastAPI backend ──▶ orchestrator (retrieve → generate)
                              │                    │
                              ▼                    ├──▶ Claude Agent SDK ──▶ Anthropic API
                        Postgres + pgvector         └──▶ httpx client ──────▶ Ollama (chat + embed)
```

Retrieval is always a deterministic server-side step (never a model-decided tool call), so grounding behavior is identical regardless of which provider is active. Full rationale in `architecture.md` → "Agent routing / model toggle".

## Prerequisites

- Docker + Docker Compose v2 (`docker compose version`)
- ~8GB free RAM if running the default `llama3.1:8b` local model (see below for lighter alternatives)
- Optional: an Anthropic API key for the cloud path (`ANTHROPIC_API_KEY`) — **not required**, the local Ollama path works with zero keys

## Quickstart (one command)

```bash
cp .env.example .env
make up          # or: docker compose up --build
```

This starts Postgres (with pgvector), Ollama, the FastAPI backend, and the frontend. On first boot, the `ollama-init` service pulls the configured chat + embedding models — `llama3.1:8b` is ~4.9GB, budget 5-15 minutes depending on your connection. Once it's up:

```bash
make ingest       # populate the knowledge base from data/transcripts/
```

**Timing, measured on CPU-only hardware (no GPU):** ingesting all 36 vendored transcripts takes **~40 minutes** (one embedding call per chunk, ~2,500 chunks total) — it's a one-time step, and safe to re-run anytime afterward (content-hash based, re-runs finish in seconds by skipping unchanged files). A single grounded chat reply from the default `llama3.1:8b` takes **~1-2 minutes** on CPU alone; a GPU or Apple Silicon (Metal) machine will be dramatically faster on both. If you want a faster demo loop while developing, swap `OLLAMA_MODEL` for a smaller model (see the env var table below) — ingestion time is dominated by the embedding model, not the chat model, so `OLLAMA_EMBED_MODEL` is what to swap for faster ingestion specifically.

Then open **http://localhost:5173**.

The backend runs Alembic migrations automatically on startup. The `db` container's host-exposed port defaults to **5433** (not 5432), since many dev machines already run a local Postgres — the backend itself always talks to `db:5432` over the internal Docker network regardless.

## Environment variables

See `.env.example` for the full annotated list. The essentials:

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | Process-wide default; a session can override it live in the UI. |
| `ANTHROPIC_API_KEY` | _(empty)_ | Only needed to use the Claude cloud path. |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` | |
| `OLLAMA_MODEL` | `llama3.1:8b` | Swap for `qwen2.5:3b` or `phi3.5` on machines with <16GB RAM. |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Used for retrieval regardless of chat provider. |
| `DATABASE_URL` | (docker-compose sets this) | Only needed if running the backend outside Docker. |

## Local vs. cloud model setup

- **Local (mandatory demo path, zero keys required)**: `docker compose up` already brings up Ollama and pulls `OLLAMA_MODEL`/`OLLAMA_EMBED_MODEL`. Leave `LLM_PROVIDER=ollama` (the default) and it just works.
- **Cloud**: set `ANTHROPIC_API_KEY` in `.env`, restart (`docker compose up -d backend`), then either set `LLM_PROVIDER=anthropic` or switch it live from the provider toggle in the top bar — no code changes, no rebuild.

## Running outside Docker (optional, for backend development)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://lenny:lenny@localhost:5433/lenny
export OLLAMA_BASE_URL=http://localhost:11434
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
make test          # full suite (pytest) inside the backend container
make test-unit      # pure unit tests only — no live Postgres required
```

Or locally: `cd backend && pytest` — the retrieval/chunking/Ship 30 validator/artifact-detection tests are pure unit tests and always run; the API/persistence tests in `tests/test_sessions_api.py` need a reachable Postgres (`docker compose up -d db`) and skip gracefully with a clear reason if one isn't available.

See `tests/manual_test_plan.md` for the UI flows that need a human (rendering, the artifact sandbox, responsive/keyboard behavior).

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `docker compose up` fails to bind port 5432 | Something else on the host already listens there — this repo maps the db container to host port **5433** by default for exactly this reason; check `POSTGRES_HOST_PORT` in `.env` if you changed it. |
| Chat requests fail with `provider_unavailable` | Check `GET /health` — it reports `db`, `ollama`, and `anthropic` independently. For Ollama, confirm `docker compose ps` shows it healthy and the model finished pulling (`docker compose logs ollama-init`). |
| Every answer says "the transcripts don't cover this" | You haven't run `make ingest` yet, or `RETRIEVAL_MIN_SCORE` is too high for your embedding model — check `GET /api/sources` for ingested counts. |
| Ship 30 essay looks off-format | The validator auto-repairs once; if the second draft still fails, that's surfaced as a warning in the backend logs (`ship30_repair_still_failing`) rather than silently returned as-is being hidden — check backend logs. |
| Frontend can't reach the backend | Confirm `VITE_API_BASE_URL` matches where the backend is actually listening (`http://localhost:8000` by default) and that `CORS_ORIGINS` on the backend includes the frontend's origin. |
| `alembic upgrade head` fails with a missing extension error | The `db` image must be `pgvector/pgvector:pg16` (already set in `docker-compose.yml`) — a plain `postgres` image won't have the `vector` extension available. |
| A grounded question times out (`provider_timeout`, 504) | Expected on CPU-only hardware with the default `llama3.1:8b` if it takes longer than `PROVIDER_TIMEOUT_SECONDS` (240s default, already sized above the ~2-minute measured worst case) — raise it further, or switch to a smaller `OLLAMA_MODEL` for a faster loop. |
| Answers cite a plausible-looking but *wrong* source (rare) | Retrieval intentionally uses an exact sequential scan, not an approximate index — see the comment in `backend/migrations/versions/0001_initial.py` for why an `ivfflat` index isn't used here (it silently produces wrong nearest-neighbors when built before ingestion, which is confirmed and documented, not a theoretical concern). |

## Repository layout

```
backend/         FastAPI app, agent/RAG layer, Alembic migrations, pytest suite
frontend/        React/Vite/Tailwind chat UI + artifact viewer
data/transcripts/ Vendored transcript subset (see data/transcripts/README.md)
scripts/ingest.py Idempotent knowledge-base ingestion CLI
agent-transcripts/ Build-session logs, including corrected mistakes
tests/manual_test_plan.md  Human UI test plan
PRD.md / design.md / architecture.md  Full discovery brief, UX rationale, and technical design
```

## Scope simplifications (see PRD.md for the full list)

- Frontend runs via the Vite dev server inside Docker rather than a production nginx build — simplest reliable "one-command startup" for an evaluator; swap for a multi-stage static build for real deployment.
- No auth — single-tenant local demo with a client-generated pseudo-user id.
- Response streaming (SSE) was cut in favor of a synchronous call + typing indicator, given the time budget.
