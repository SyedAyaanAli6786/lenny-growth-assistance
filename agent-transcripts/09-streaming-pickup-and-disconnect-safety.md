# Session log — Resuming interrupted work: streaming, and a bug it exposed

Opened this session to an uncommitted working tree: a prior agent conversation
had already written token-by-token streaming for both providers, disabled
Ollama's "think" mode's follow-on plumbing, and session auto-naming — but had
been force-exited before committing or verifying any of it. The user's brief
was "why is Ollama slow, why isn't the chat getting named, continue this work
and don't ask for permission on routine steps." Rather than trust the diff was
correct, ran it for real before touching anything else.

## Verified the inherited work, live

Started the real backend against the real Postgres/Ollama stack (not the test
suite) and drove `POST /api/sessions/{id}/messages/stream` with `curl` for
several real questions. Confirmed: deltas stream in as the model produces
them, the session gets titled from its first message, and a full reply with
citations persists correctly. Also confirmed the actual, current bottleneck:
`qwen3:8b` on this CPU-only machine (`size_vram: 0` in `ollama ps` — no GPU)
genuinely takes 50–120+ seconds per grounded reply. Streaming doesn't reduce
that; it turns a blank multi-minute wait into visible incremental progress,
which is the actual usability problem worth solving here — documented later
in the PRD's "Scope choices" (see entry 11).

## Bug found and fixed: a slow stream could lose the user's own message

Timing this streaming endpoint required leaving `curl` running for 1-2
minutes per question. During one of those tests, killing the client early (to
move on to something else) surfaced a real defect: the user's message and the
session title were only ever persisted in the `done` branch, together with the
assistant's reply, at the very end of generation. Starlette cancels a
`StreamingResponse`'s generator outright on client disconnect — and because
replies now legitimately take 50-120+ seconds, a disconnect mid-stream (tab
closed, laptop slept, network dropped, or simply the browser's own timeout)
is a real risk over that window, not a hypothetical one. Confirmed the failure
directly: killed a live stream 5 seconds in, and the session came back with
`"messages": []` — the user's own question was gone with no trace it was ever
sent, and the session stayed untitled.

Fixed by splitting `_persist_turn()` into `_persist_user_message()` and
`_persist_assistant_message()` (`backend/app/api/sessions.py`), and calling
the user-message half immediately when the streaming request starts, before
generation begins — not alongside the reply at the end. Re-verified with the
same kill-mid-stream test: the user's message and title now survive a
disconnect that happens before the reply lands. Added
`test_send_message_stream_persists_user_message_even_if_generation_fails`
(simulates a mid-stream provider crash rather than a real network kill, for a
fast, deterministic regression test) — all 36 backend tests passed after this
fix, up from 35.
