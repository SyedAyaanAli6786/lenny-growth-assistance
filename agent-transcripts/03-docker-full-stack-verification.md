# Session log — Full Docker stack verification with the user

Follow-up session: the user asked for a plain-language list of everything still
unverified or missing, then asked me to work through everything I could do
without them (an Anthropic API key and a connected browser were the two things
only they could provide). This log covers that self-doable pass.

## What was run, for real, exactly as documented

- Added a repo-root `.dockerignore` (there wasn't one) — without it,
  `frontend/Dockerfile`'s `COPY frontend/ ./` after `npm install` would have
  copied the *host's* `frontend/node_modules` into the image, on top of the
  container's own install, risking a broken `esbuild` native binary. Verified
  after the fix by checking `node_modules/.bin/vite` inside the running
  container resolves correctly.
- Ran `docker compose up --build -d` — all five services (db, ollama,
  ollama-init, backend, frontend) started from a clean state, exactly as the
  README's "Quickstart" section describes.
- `docker compose exec backend pytest` — all 32 tests passed inside the real
  container (this also caught and fixed a bug: `backend/Dockerfile` never
  copied `backend/tests/` or `pytest.ini` into the image at all, so this
  command would have found zero tests before the fix).
- Live-tested `PATCH /api/sessions/{id}/provider` against the running
  container (not mocked): switching to `ollama` returns 200; switching to
  `anthropic` with no key configured returns a structured 503
  `provider_unavailable` rather than a crash.
- Ran the full ingestion of all 36 vendored transcripts through
  `docker compose exec backend python -m scripts.ingest` (the actual `make
  ingest` command) — 2,533 chunks across 36 sources, ~40 minutes on CPU-only
  embedding calls. Re-ran it a second time immediately after: every file
  correctly skipped as unchanged in under 4 seconds, confirming the
  content-hash idempotency actually works, not just in theory.
- Caught a bug in that same ingest run: `scripts/ingest.py`'s file glob
  (`*.md`) would also match `data/transcripts/README.md` and try to ingest it
  as a fake transcript source. Fixed by excluding any file whose stem is
  `readme` (case-insensitive), before it could pollute the real ingestion run.

## The most important bug this session found

Asked a real grounded question ("What does Sean Ellis say about the 40 percent
test for product market fit?") against the live, fully-ingested knowledge
base — Sean Ellis's own transcript is in there — and got back "There is no
mention of Sean Ellis... in the provided transcripts," citing two completely
unrelated episodes instead.

Diagnosed by running the retrieval query twice directly against Postgres: once
through the normal path (uses the `ivfflat` index from the initial migration),
and once with `enable_indexscan`/`enable_bitmapscan` turned off to force an
exact sequential scan. The indexed query never returned Sean Ellis's transcript
in its top 10 at all; the sequential scan returned nothing *but* Sean Ellis in
its top 10, with real similarity scores (0.80, 0.80, 0.73...) versus the
indexed path's wrong, low scores (0.60, 0.57...).

Root cause: the `ivfflat` index is created in the Alembic migration, which
always runs against an empty `transcript_chunks` table — ingestion happens
afterward. `ivfflat`'s cluster centroids are trained from whatever data exists
*at index-creation time*, so building it on an empty table produces a
degenerate index that silently returns wrong nearest neighbors instead of
erroring. This is a documented pgvector gotcha I hadn't accounted for, and it
directly broke the one thing this whole assignment is graded hardest on:
reliable, grounded, correctly-cited answers.

Fix: removed the `ivfflat` index from the migration entirely rather than
adding a `REINDEX`-after-ingest step. At this project's actual scale (~2,500
chunks), an approximate index buys nothing — pgvector's exact sequential scan
over a few thousand 768-dim vectors is fast, and correctness matters far more
than speed at this size. Applied the fix to the live test database
(`DROP INDEX`), re-ran the exact same question through the real API, and got a
correct, well-cited, accurately-quoted answer this time (citing the real Sean
Ellis transcript at 0.80 relevance). Documented the trade-off in the migration
file itself for anyone who scales the knowledge base up later.

## The other significant finding: real latency numbers

The same re-test also surfaced that the original `PROVIDER_TIMEOUT_SECONDS=60`
default was far too low for the *documented* default model. Measured directly:
CPU-only `llama3.1:8b` with a full grounded system prompt (5 retrieved chunks)
took 200+ seconds for a single reply with no GPU; even at `RETRIEVAL_TOP_K=3`
it's ~2 minutes. Every prior test in this build had used a tiny `qwen2.5:0.5b`
model for speed, which never surfaced this — the documented default is much
slower.

Changed two defaults (`backend/app/config.py` and `.env.example`, kept in
sync): `RETRIEVAL_TOP_K` 5→3 (smaller prompt, less marginal context) and
`PROVIDER_TIMEOUT_SECONDS` 60→240 (headroom above the measured worst case,
rather than have the mandatory local-demo path fail by default on exactly the
hardware it's meant to run on). Updated the PRD's operational success metric
and Latency risk row to state the measured numbers plainly instead of the
earlier, untested "under 2 minutes" claim — narrowed that metric to "stack
ready to accept a question," since the reply itself genuinely can't hit that
bar on CPU alone without a smaller/faster model.

## What's still not verified

Everything requiring the user's own accounts/tools: the Anthropic cloud path
(no API key available in this environment), and anything requiring an actual
browser (Chrome extension wasn't connected here) — visual UI rendering, the
HTML artifact sandbox escape test, responsive/mobile layout, keyboard-only
navigation.
