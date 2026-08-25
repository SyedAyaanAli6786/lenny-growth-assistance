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

- **Ollama** installed natively (mandatory per the brief — the demo must run local inference): [ollama.com](https://ollama.com)
- **Python 3.11+** and **Node 20+** for the backend/frontend
- Docker (optional — see below)
- ~8GB free RAM for an 8B-class local model (see below for lighter alternatives)
- Optional: an Anthropic API key for the cloud path (`ANTHROPIC_API_KEY`) — **not required**, the local Ollama path works with zero keys

## A note on Docker

The brief asks for "a practical setup path, **ideally using Docker Compose or an equivalent reproducible workflow**" — Docker is a suggestion, not a requirement; only Ollama itself is mandatory. This repo's actual recommended path runs the backend and frontend **natively** (venv / `npm run dev`) against a **natively-installed Ollama**, using Docker only for the lightweight, disposable `db` (Postgres+pgvector) container — that avoids a system-wide Postgres install without any of Docker's heavier costs. A full `docker-compose.yml` is still included and works (`make up`) for anyone who prefers a single fully-containerized command, but be aware it pulls Ollama models into a **second, separate copy** inside a Docker volume — redundant (and multi-GB) if you already have Ollama running natively, which is exactly why the native path is the default recommendation here.

## Quickstart (native — recommended)

```bash
cp .env.example .env
cp .env.example backend/.env   # then edit ports/model in backend/.env if you want them to differ from .env

ollama pull qwen3:8b           # or any model comfortable on your machine
ollama pull nomic-embed-text   # embedding model, used for retrieval regardless of chat model

docker compose up -d db        # Postgres+pgvector only — lightweight, no model downloads
```

Run migrations and ingest the knowledge base once:
```bash
cd backend
export DATABASE_URL=postgresql+asyncpg://lenny:lenny@localhost:5433/lenny
./.venv/bin/alembic upgrade head
cd ..
PYTHONPATH=backend backend/.venv/bin/python3 -m scripts.ingest
```

Then, in separate terminals:
```bash
make backend    # or: cd backend && ./.venv/bin/uvicorn app.main:app --port 3400
```
```bash
cd frontend && npm run dev     # port 3500 (vite.config.ts's default)
```

Open **http://localhost:3500**.

**Timing, measured on CPU-only hardware (no GPU):** ingesting all 36 vendored transcripts takes **~40 minutes** (one embedding call per chunk, ~2,500 chunks total) — it's a one-time step, and safe to re-run anytime afterward (content-hash based, re-runs finish in seconds by skipping unchanged files). A single grounded chat reply takes **~1-2 minutes** on CPU alone with an 8B-class model; a GPU or Apple Silicon (Metal) machine will be dramatically faster on both.

## Quickstart (fully Dockerized alternative)

```bash
cp .env.example .env
make up          # or: docker compose up --build
```
Starts Postgres, Docker's own Ollama (pulls `OLLAMA_MODEL`/`OLLAMA_EMBED_MODEL` into its own volume before `backend` finishes starting), the backend (port 3400), and frontend (port 3500) together — genuinely one command, no separate pull step, at the cost of a second model download if you already have Ollama natively. Then `make ingest`. Open **http://localhost:3500**.

The backend runs Alembic migrations automatically on startup. The `db` container's host-exposed port defaults to **5433** (not 5432), since many dev machines already run a local Postgres — the backend itself always talks to `db:5432` over the internal Docker network regardless. Similarly, Docker's `ollama` service exposes no host port at all (only reachable at `ollama:11434` inside the compose network) specifically to avoid colliding with a native Ollama install already using host port 11434.

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

- **Local (mandatory demo path, zero keys required)**: install Ollama, `ollama pull` your chosen chat + embedding models, leave `LLM_PROVIDER=ollama` (the default), and it just works — no keys needed anywhere.
- **Cloud**: set `ANTHROPIC_API_KEY` in `.env`/`backend/.env`, restart the backend, then either set `LLM_PROVIDER=anthropic` or switch it live from the provider toggle in the top bar — no code changes, no rebuild.

## First-time setup (native path)

Only needed once — installs the backend's Python deps into a venv and the frontend's npm deps:

```bash
cd backend && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cd ../frontend && npm install
```

After that, the commands in "Quickstart (native — recommended)" above are all you need for every subsequent run.

## Tests

```bash
cd backend && ./.venv/bin/pytest
```
The retrieval/chunking/Ship 30 validator/artifact-detection tests are pure unit tests and always run; the API/persistence tests in `tests/test_sessions_api.py` need a reachable Postgres (`docker compose up -d db`) and skip gracefully with a clear reason if one isn't available.

If you're using the fully-Dockerized alternative instead: `make test` (full suite inside the backend container) or `make test-unit` (pure unit tests only).

See `tests/manual_test_plan.md` for the UI flows that need a human (rendering, the artifact sandbox, responsive/keyboard behavior).

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `docker compose up` fails to bind port 5432 | Something else on the host already listens there — this repo maps the db container to host port **5433** by default for exactly this reason; check `POSTGRES_HOST_PORT` in `.env` if you changed it. |
| `docker compose up` fails to bind port 11434 | A native Ollama install is already using it — Docker's own `ollama` service doesn't expose a host port at all by default for exactly this reason; if you changed that, revert it or stop the native install first. |
| Chat requests fail with `provider_unavailable` | Check `GET http://localhost:3400/health` — it reports `db`, `ollama`, and `anthropic` independently. For Ollama, confirm `docker compose ps` shows it healthy and the model finished pulling (`docker compose logs ollama-init`). |
| Every answer says "the transcripts don't cover this" | You haven't run `make ingest` yet, or `RETRIEVAL_MIN_SCORE` is too high for your embedding model — check `GET /api/sources` for ingested counts. |
| Ship 30 essay looks off-format | The validator auto-repairs once; if the second draft still fails, that's surfaced as a warning in the backend logs (`ship30_repair_still_failing`) rather than silently returned as-is being hidden — check backend logs. |
| Frontend can't reach the backend | Confirm `VITE_API_BASE_URL` matches where the backend is actually listening (`http://localhost:3400` by default) and that `CORS_ORIGINS` on the backend includes the frontend's origin (`http://localhost:3500` by default). |
| `alembic upgrade head` fails with a missing extension error | The `db` image must be `pgvector/pgvector:pg16` (already set in `docker-compose.yml`) — a plain `postgres` image won't have the `vector` extension available. |
| A grounded question times out (`provider_timeout`, 504) | Expected on CPU-only hardware if it takes longer than `PROVIDER_TIMEOUT_SECONDS` (500s default, sized above the measured worst case for a full Ship 30 essay) — raise it further, or switch to a smaller `OLLAMA_MODEL` for a faster loop. |
| Answers cite a plausible-looking but *wrong* source (rare) | Retrieval intentionally uses an exact sequential scan, not an approximate index — see the comment in `backend/migrations/versions/0001_initial.py` for why an `ivfflat` index isn't used here (it silently produces wrong nearest-neighbors when built before ingestion, which is confirmed and documented, not a theoretical concern). |

## Extending the system

### Add a new LLM provider

1. Implement the `LLMProvider` interface (`backend/app/agent/base.py`): `generate()`, `generate_stream()`, `is_available()`, plus `name` and `model_name`. `AnthropicProvider` and `OllamaProvider` (`backend/app/agent/`) are the two reference implementations — a third follows the same shape.
2. Register it in `get_provider()` (`backend/app/agent/orchestrator.py`) — add an `elif name == "your_provider": _PROVIDERS[name] = YourProvider()` branch.
3. Add its config (base URL / API key / model name) to `Settings` in `backend/app/config.py`, and document the new variables in `.env.example`.
4. Widen the `Literal["anthropic", "ollama"]` provider type in `backend/app/api/schemas.py` (`ProviderUpdate.provider`) and the matching `Provider` type in `frontend/src/types.ts`, then add an option to `frontend/src/components/ProviderToggle.tsx`.
5. Nothing else changes: `orchestrator.py`'s retrieval, prompt construction, and citation/artifact parsing are provider-agnostic by design, so a new provider only has to implement generation.

### Add a new skill (beyond Ship 30 for 30)

Follow the pattern in `backend/app/agent/skills/ship30.py`: a structured prompt template (not a one-off string) plus a `validate_*` function that mechanically checks the output against the skill's actual requirements — word count, required structure, required elements — with a repair-prompt builder for one automatic retry rather than silently returning a malformed draft. Wire it up with a new orchestrator function (mirroring `run_ship30()`) and a new endpoint (mirroring `POST /api/sessions/{id}/ship30`).

### Ingest different or additional transcripts

`scripts/ingest.py` is idempotent and re-runnable against any directory of markdown files with YAML frontmatter (`title`, `guest`, `url`/`youtube_url`, `date`/`published_at`/`publish_date`):

```bash
PYTHONPATH=backend backend/.venv/bin/python3 -m scripts.ingest --path <your-directory>
```

Unchanged files are skipped (compared via a content hash); changed files have their chunks replaced and re-embedded. To pull more episodes from the source archive (`github.com/ChatPRD/lennys-podcast-transcripts`), clone it, copy the desired `episodes/<guest>/transcript.md` files into `data/transcripts/<slug>.md`, and re-run ingestion — no code changes required.

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
