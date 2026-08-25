# PRD — The Lenny Growth Assistant

## 1. Forward Deployment Brief

### User and problem

**Primary user**: a PM, growth lead, or founder inside the client's product/growth org who wants a fast, trustworthy answer to a specific product/growth question ("how should we think about activation for a PLG product," "what does Lenny's guests say about pricing experiments") without listening to hours of podcast audio or trusting an ungrounded chatbot.

**Job to be done**: turn a question into (a) a grounded answer with a pointer back to which episode it came from, and (b) optionally a reusable written artifact (an essay, a doc, a one-pager) they can hand to someone else — without needing to know what a "prompt," "model," or "vector index" is.

**Pain removed**: today this knowledge lives in ~300 hours of podcast audio. Finding it means remembering which episode, scrubbing to the right timestamp, and then still having to write up the takeaway themselves. The assistant collapses "search + synthesize + draft" into one conversational loop, and never presents an answer without saying where it came from.

### Success metric

Primary (product): **≥90% of answers cite at least one transcript source, and 0% of answers state a claim the retrieved chunks don't support** — checked by the automated grounding-fallback behavior (Section 4.1) and spot-checked in the manual test plan. This is the metric that matters for a "reliable internal assistant" brief: an ungrounded but articulate answer is worse than a correctly-declined one.

Secondary (operational): **local (Ollama) demo path starts and the container stack is ready to accept a question in under 2 minutes on a clean machine** (model pull excluded — that's a one-time, bandwidth-bound download, not a startup cost). This is narrower than an earlier draft of this metric, which also implied the *first answer itself* would land under 2 minutes — live testing showed CPU-only `llama3.1:8b` answering a real grounded question takes closer to 2 minutes on its own (see the Latency risk below), so holding the reply itself to that bar isn't realistic on CPU-only hardware without shrinking the model or context further than the demo quality warrants.

### Assumptions

The brief was intentionally incomplete in places. Assumptions made to fill the gaps:

- **Transcript source**: the assignment's own embedded hyperlink for the transcript repository points to `github.com/ChatPRD/lennys-podcast-transcripts`. We vendor a curated subset (50 episodes, selected by view count from the full 303-episode archive) into the repo rather than pulling live from GitHub at evaluation time, so the demo doesn't depend on an external repo's availability, rate limits, or future changes.
- **Single-tenant, no auth**: "user metadata" is a client-generated pseudo-user id kept in `localStorage`, not a login system. The brief doesn't ask for multi-user auth, and building one would eat time better spent on grounding quality and ops readiness.
- **One cloud provider is enough**: the brief says "at least one" — Anthropic Claude is used both because it's required for the agent layer anyway and to avoid maintaining two independent prompt/tool surfaces. OpenAI is documented as a drop-in extension point, not implemented.
- **Embeddings are local-only**: Ollama's `nomic-embed-text` embeds transcripts regardless of which chat provider (Claude or Ollama) is currently selected. This keeps retrieval quality constant across the toggle and keeps the knowledge base usable with zero cloud keys — but it caps embedding quality at what a small local model can do (see Risks).
- **"Switch without changing application code"** is read as *config-only* (an env var / a per-session dropdown), not requiring a hot-swappable plugin architecture beyond that.
- **Artifacts are triggered by conversational intent** ("write this up as a doc," a `/ship30` action, generating markdown/HTML in the reply) rather than a separate authoring mode.

### Scope choices

**Included**: grounded RAG chat with citations and follow-up context; a cloud/local model toggle visible in the UI; token-by-token response streaming for both providers; a structured Ship 30 for 30 skill (not a one-off prompt); a markdown/HTML artifact viewer with an explicit, documented sandboxing policy; Postgres-backed session/message/artifact persistence; a one-command startup path (see below); structured logs and graceful failure handling for the listed failure modes; automated tests for the critical paths; full handoff docs.

**Startup path — native-first, not Docker-first**: the brief asks for "a practical setup path, ideally using Docker Compose or an equivalent reproducible workflow" — Docker Compose is offered as a suggestion, not required, and only Ollama itself is mandatory. The recommended path here runs the backend/frontend natively (venv / `npm run dev`) against a natively-installed Ollama, using Docker only for the lightweight `db` (Postgres+pgvector) container. This was a real, empirically-forced decision, not a preference: running the full stack in Docker means Ollama's models get pulled a *second* time into an isolated Docker volume even when already present natively, and on a disk that's already tight that redundant multi-GB pull is what actually exhausted available disk space during testing (see `agent-transcripts/07-disk-exhaustion-and-docker-scope-change.md`). A complete `docker-compose.yml` is still included and works end-to-end (`make up`) for an evaluator who prefers a single fully-containerized command and has the disk headroom for it.

**Response streaming — added after testing, not the stretch goal an earlier draft of this PRD called it**: the brief itself never asks for streaming, so it was initially scoped out. Live testing reversed that decision: CPU-only Ollama measured 50–120+s per grounded reply (see the Latency risk below), and a chat UI that shows nothing for two minutes reads as frozen, not "thinking" — directly undermining the trust this brief evaluates the system on. Streaming doesn't reduce total latency (the model still takes as long to finish); it replaces a blank wait with visible incremental progress, which is the actual usability problem worth solving on CPU-only hardware. Implemented for both providers so behavior stays consistent across the toggle: Ollama via `stream: true` on `/api/chat` forwarded as NDJSON from a dedicated `/messages/stream` endpoint, Anthropic via the Claude Agent SDK's partial-message events. This also forced a related, non-optional fix: because the wait is now long enough that a client disconnect mid-stream (tab closed, network drop) is a real risk rather than a corner case, the user's message is persisted the moment the request starts rather than alongside the reply at the end — otherwise a dropped connection would silently lose the user's own message with no trace it was ever sent.

**Excluded, deliberately**: authentication/authorization, multi-tenant isolation beyond a client-side pseudo-id, a second cloud provider, a general-purpose intent classifier for the Ship 30 skill, production autoscaling/rate limiting, and any transcript ingestion beyond the vendored subset (the ingestion *pipeline* is built to be re-run against the full 303-episode repo, but the demo ships a curated 50).

### Risks and trade-offs

| Risk | Mitigation |
|---|---|
| **Hallucination** | Deterministic retrieval-then-generate (not model-decided tool calls); system prompt requires citing chunk ids. When *nothing* clears the relevance threshold, the backend returns a fixed decline message without calling the model at all — this was tightened from a prompt-only instruction after live testing showed a small local model would confidently answer an off-topic question from its own knowledge (and our citation fallback logic would misattribute it to an unrelated transcript) rather than decline; see `agent-transcripts/02-verification-and-fixes.md`. When *some* marginal grounding exists, the system prompt still governs the answer — this residual case isn't fully solved. |
| **Agent SDK is Claude-only, but Ollama is mandatory for the demo** | Retrieval is a shared deterministic step so grounding behavior doesn't change by provider; the Claude Agent SDK drives generation for the cloud path, a matching `OllamaProvider` (same interface, same prompts) drives it locally. Documented here rather than silently picking one requirement over the other. |
| **Local model quality** | Small local models are weaker at following citation format and long-form structure than Claude. Mitigated with a stricter, more explicit local system prompt and the Ship 30 skill's validator/repair pass, which catches format drift regardless of provider. |
| **Latency** | Measured, not estimated: CPU-only `llama3.1:8b` with a 3-chunk grounded prompt took ~2 minutes per reply in testing (no GPU), and a full Ship 30 essay measured ~384s even with a faster model's reasoning overhead disabled — pure generation-length cost. `RETRIEVAL_TOP_K` defaults to 3 (not 5) and `PROVIDER_TIMEOUT_SECONDS` to 500 specifically because of these measurements — see `agent-transcripts/03-docker-full-stack-verification.md` and `04-qwen3-characterization.md`. A GPU or Apple Silicon (Metal) machine finishes in a few seconds regardless. This directly affects the "sub-2-minute cold start" operational success metric above on CPU-only hardware — flagged here rather than smoothed over. |
| **Cost** | Cloud path costs tokens per message; no budget guardrail is implemented beyond documenting it — out of scope for a local take-home demo, called out for a real deployment. |
| **Data leakage** | Transcripts are public podcast content, but generated artifacts (HTML/Markdown) could echo back chat content. Artifacts are scoped to a session and not shared cross-session; no third-party network calls happen from generated HTML (see sandboxing). |
| **Unsafe artifact rendering** | Generated HTML is untrusted by construction. Rendered in a `srcdoc` iframe with `sandbox="allow-scripts"` only (no `allow-same-origin`), plus an injected CSP blocking network egress — detailed in `architecture.md`. |
| **DB/Ollama unavailability** | `/health` reports per-component status; API calls fail with structured 503s instead of 500s; the app degrades (e.g., cloud-only if Ollama is down) rather than crashing. |

---

## 2. Product Requirements

### Users

- **Primary**: PM/growth practitioner asking product and growth questions.
- **Secondary**: the FDE/client engineer evaluating and operating the system (README/architecture.md serve them directly).

### Problem statement

Give the primary user grounded, cited answers from Lenny's Podcast/Newsletter content, plus the ability to turn a conversation into a polished, reusable artifact, in a tool they can run and trust without understanding the underlying AI stack.

### Success metric

See Forward Deployment Brief above — citation coverage / zero-unsupported-claims as the primary product metric, sub-2-minute local cold start as the operational metric.

### Core user flows

1. **New grounded question** → user opens a new session → asks a product/growth question → assistant retrieves top-k relevant transcript chunks → answers with inline citations (episode + guest) → citations are visible/expandable in the UI.
2. **Follow-up** → user asks a clarifying/related question in the same session → prior turns + new retrieval are used → context is preserved.
3. **No-coverage question** → user asks something the transcripts don't cover → assistant explicitly says so instead of guessing, with zero fabricated citations.
4. **Provider switch** → user (or evaluator) switches the model dropdown between Claude and Ollama → next message in the same session runs on the new provider → the active provider/model is always visible in the UI.
5. **Ship 30 for 30 essay** → user asks for the current answer/topic "as a Ship 30 essay" (or clicks the action) → the skill produces a ~1,250-word, headed, bolded, grounded essay with a validator pass → rendered as a markdown artifact.
6. **Artifact generation** → user asks for a doc/HTML snippet → assistant emits a fenced markdown/HTML block → backend detects and persists it as an artifact → frontend renders it in the Artifact Viewer beside the chat, sandboxed if HTML.
7. **Failure states** → Ollama down, DB down, missing Anthropic key, retrieval timeout → user sees a clear, specific error, not a stack trace or a silent hang.

### Acceptance criteria

- A fresh clone, following either the native quickstart or `docker compose up` (with `.env` from `.env.example`), serves a working chat UI without any cloud API key, using Ollama end to end.
- Every grounded answer either includes ≥1 transcript citation or explicitly states the knowledge base doesn't cover the question — never both uncited and confidently specific.
- Switching the provider dropdown changes which backend path serves the next message, without restarting the app or editing code.
- The Ship 30 output is validated for approximate word count (1,000–1,500), presence of headings, at least one bolded phrase, and a clear takeaway; a failing draft is auto-repaired once before being returned.
- An HTML artifact containing a `<script>` that attempts `fetch()`, `window.top` access, or a form post cannot reach the network or the parent page — verified in the manual test plan.
- `/health` reports DB, Ollama, and Anthropic-key status independently, and the app stays usable in a degraded (partial-provider) state.
- `pytest` passes for chunking, retrieval ranking, session/message persistence, the Ship 30 validator, and API contract/error-path tests.

### Implementation plan

See the approved build plan (repo scaffolding → PRD/design/architecture docs → backend scaffolding → LLM config layer → knowledge base ingestion → grounded assistant → Ship 30 skill → artifact viewer → frontend → deployment/ops → tests → README → agent transcripts). Tracked phase-by-phase in `agent-transcripts/`.
