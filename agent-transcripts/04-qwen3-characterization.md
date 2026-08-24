# Session log — Characterizing qwen3:8b as an alternative local model

The user downloaded `qwen3:8b` + `nomic-embed-text` via a native (non-Docker) Ollama
install on the same host, and asked whether it would work with this app before
committing more time to it. Answered directly first (no code changes), then — once
they confirmed both models were pulled — actually tested it end to end against the
real backend, per their earlier "go ahead and do the self-doable items" instruction.

## Setup

Rather than re-pull models into the separate Dockerized `ollama` service (which
has its own volume, distinct from the host's native Ollama), pointed the backend's
`OLLAMA_BASE_URL` at the host's already-running native Ollama (`localhost:11434`)
directly, with Postgres via `docker compose up -d db`. Faster than duplicating a
~5GB download into a second, isolated Ollama instance for what was fundamentally a
model-characterization question, not a re-verification of the Docker stack itself
(already verified in the previous session).

## Finding 1: no `<think>`-tag leakage — verified, not just assumed

Qwen3 is a hybrid reasoning model with "thinking" on by default. Checked the raw
Ollama `/api/chat` response directly: it returns `message.thinking` as a field
separate from `message.content`. `OllamaProvider.generate()` only ever reads
`.content`, so no code change was needed here — the separation is already correct
by construction. Confirmed with a real grounded question: the final answer text
was clean, well-formatted, and accurately cited, no stray reasoning text.

## Finding 2: thinking mode is a large, hidden latency cost — fixed

A trivial "What is 2+2?" prompt took **36 seconds** with thinking on
(34.5s of that was the hidden reasoning pass) versus **2.5 seconds** with
Ollama's `think: false` request parameter. Verified `think: false` is safe to
send unconditionally: a non-thinking model (`qwen2.5:0.5b`) returns 200 OK and
behaves normally when it receives a parameter it doesn't use. Added `"think":
false` to every request in `ollama_provider.py` — since the app never reads
`message.thinking` anyway, disabling it is a pure win with no observed downside,
for any Ollama model, not just qwen3.

Effect on the real grounded-chat path: **210s → 63s** for the same question, same
citation accuracy, same answer quality (arguably better organized — bullets, bold
emphasis, more synthesis than the llama3.1:8b answer from the prior session, which
tended to quote more directly).

## Finding 3: Ship 30's slowness is real generation cost, not reasoning overhead

Even with `think: false`, a single Ship 30 draft call measured **384s** (~1000
words generated). A live end-to-end test through the actual API hit two rounds
(initial draft 792 words, failed the 1250±250 word-count check; the repair pass
also came back at 792 words, still failing) — each individual `generate()` call
stays under any reasonable per-call timeout, but the *total* HTTP response time is
additive across both calls when a repair pass fires, since they run sequentially
within one request handler. Confirmed via server logs that the real run completed
in roughly 9-10 minutes total; my own `curl --max-time` test client gave up first
and reported a false failure — the backend itself handled it correctly (returned a
response, no crash, no hang), it was just slower than my test harness's patience.

Raised `PROVIDER_TIMEOUT_SECONDS` from 240 to 500 (`backend/app/config.py` and
`.env.example`, kept in sync) — enough headroom above the measured 384s single-call
worst case, while being honest in both places that Ship 30 with a repair pass can
still take several minutes wall-clock even though no single call approaches the
timeout ceiling.

## Open question left to the user

Two viable local models now, with different trade-offs:
- `llama3.1:8b` (current documented default): the one verified through the full
  Docker Compose stack end to end (migrations, ingestion, chat, tests). Ship 30
  latency specifically was never isolated for it the way it was for qwen3.
- `qwen3:8b` (with `think: false`): materially faster grounded chat (~63s vs
  ~120s+), comparable-or-better answer quality and citation accuracy, but hit the
  1250-word Ship 30 target on neither of two attempts in this session (792 words
  both times) — worth more sampling before trusting it there.

Not changing the documented default unilaterally — flagged to the user as a
product call, not an engineering one.
