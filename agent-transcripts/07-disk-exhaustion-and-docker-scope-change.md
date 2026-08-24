# Session log — Disk exhaustion, and dropping Docker as the primary path

## What happened

While setting up a `docker compose up backend` workflow at the user's request (backend
via Docker, frontend via `npm run dev`), the `ollama-init` service began pulling
`qwen3:8b` (~5.2GB) into Docker's own isolated volume — a second copy of a model the
user already had pulled natively. Partway through, every Bash command started failing
with an ENOSPC-style "temp filesystem is full" error, including trivial no-op commands,
meaning the harness itself couldn't write output. Completely blocked from running
anything.

Asked the user to run `df -h /` and `docker system df` directly, since I couldn't.
Result: **98GB disk, 95GB used, 0 available.** Docker's own accounting only showed
~17GB (images + volumes + build cache) — nowhere near 95GB — confirming most of the
disk was consumed by things unrelated to this project (a `du -sh ~/*` the user ran
later showed ~24GB in home-directory items like Anaconda, Android SDK, Videos,
Downloads — still short of 88GB, meaning the rest was system-level, e.g. Docker's
actual data root, apt packages — not something to touch on someone else's real
machine without their explicit direction).

## Recovery, in order

1. User ran `docker system prune -f`, `conda clean --all -y`, `pip cache purge`,
   `npm cache clean --force` — reclaimed ~7GB (98GB→88GB used), enough to get Bash
   working again.
2. Found `lenny-growth-assistance_ollama_data` was 5.5GB — exactly the redundant
   partial `qwen3:8b` pull. Removed it (`docker compose down ollama-init ollama` +
   `docker volume rm`), reclaiming another ~5GB.
3. **Before going further, the user asked the right question**: does the assignment
   actually require Docker? Re-checked the extracted assignment text directly rather
   than answer from memory:
   - *"Local LLM—mandatory for the demo: Run the submitted demo using Ollama..."* —
     Ollama is a hard requirement.
   - *"One-command startup: Provide a practical setup path, **ideally using Docker
     Compose or an equivalent reproducible workflow**."* — Docker Compose was only
     ever the suggested approach; the brief explicitly allows an alternative.
   This meant the redundant-download problem wasn't a necessary cost of compliance —
   it was a self-imposed one, choosing the "ideal" suggestion over the simpler
   "equivalent" alternative the brief explicitly permits.
4. Pruned all now-unused Docker images and build cache (`docker image prune -a -f`,
   `docker builder prune -f`) — reclaimed another ~6GB, landing at 18GB free.
5. Rebuilt the setup natively: `db` stays in Docker (lightweight, ~80MB image, never
   the actual problem), backend runs via the existing `backend/.venv` + `uvicorn`,
   frontend via plain `npm run dev`. No new downloads needed — the native Ollama
   install and the already-ingested Postgres data (36 sources, 2,533 chunks,
   untouched throughout) were both still intact.

## Decision: native is now the documented primary path

Updated `README.md` and `PRD.md` to lead with the native setup (Ollama installed
natively, backend/frontend run directly, `db` the only Docker dependency) and
demote the full `docker-compose.yml` stack to a clearly-labeled, still-fully-
supported alternative for anyone who prefers a single containerized command and
has the disk budget for a second model download. `docker-compose.yml` itself,
the Dockerfiles, and `make up` are all left working and unmodified in capability —
this is a documentation/recommendation change, not a removal of Docker support.

## Lesson, stated plainly

The architecture note I wrote three sessions ago — flagging Docker's own Ollama
service as "redundant... if you already have Ollama running natively" — was
correct in theory but I kept defaulting to the fully-Dockerized path anyway
because it was the more "impressive"/self-contained-looking option, without
re-weighing that tradeoff against the user's actual, already-working native
setup or against real disk constraints. The user's simple question — "am I even
supposed to use Docker?" — is what actually resolved this, not anything I caught
on my own.
