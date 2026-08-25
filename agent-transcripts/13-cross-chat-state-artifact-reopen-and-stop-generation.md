# Session log — Cross-chat state bleed, artifact reopening, and stop generation

Three more issues, each reported live by the user, each traced to a real
architectural gap rather than a surface-level fix — and one of the fixes
(stop generation) took building, breaking, and rebuilding to get right.

## Bug found and fixed: chat state wasn't scoped per session

Reported live: "when I am giving a message to a particular chat, the message
is shown in every chat when it's getting generating, when I change the chat
I see the chat is generating, when the message is generated completely, then
it does not show when I change the screen." Root cause: `pendingLabel`,
`streamingText`, and `errorText` in `App.tsx` were single top-level values,
not scoped to any particular session — whichever chat happened to be on
screen when a delta or completion arrived showed it, regardless of which
chat actually started that generation. It also meant the message input was
disabled for every chat whenever any chat was generating, and a background
reply's progress became untrackable the moment you navigated away from it.

Fixed by keying all three by session id (`pendingBySession`,
`streamingBySession`, `errorBySession`), with the values shown for the
currently active session derived from those maps. Added a small pulsing
"generating" indicator in the sidebar next to a chat that's still working in
the background, since without one there'd be no signal at all once you leave
it. Verified live: sent a long message in chat A, switched to chat B while it
was still streaming — confirmed chat B showed only its own content with a
fully usable input, while the sidebar showed chat A's indicator — waited out
the full ~7-minute generation, then switched back to chat A and confirmed the
completed reply was there correctly with the indicator gone.

## Bug found and fixed: a closed artifact couldn't be reopened

Reported live: "once a document is closed after viewing it, I am unable to
reopen it." This wasn't a missing button — the frontend had genuinely nowhere
to get the data back from. `MessageOut` (what `GET /api/sessions/{id}`
returns) never carried a message's artifact at all, even though the
`Artifact` row was sitting in Postgres the whole time; only the one-time
`ChatTurnResponse` from the original request carried it, and once that state
was gone (panel closed, session switched, page reloaded) it was permanently
unreachable. Fixed by adding `artifact` to `MessageOut` and having
`GET /api/sessions/{id}` embed it from the database (a small helper,
`_messages_with_artifacts`, joins in each message's artifact by id rather
than adding an ORM relationship, avoiding async lazy-loading pitfalls). The
assistant's chat bubble now renders as a clickable button — with a "Reopen
artifact" affordance — whenever its message has one.

Verified live with the harder case, not the easy one: opened an *existing*
session with a persisted artifact fetched fresh from the database (not
carried over in React state from the original request), confirmed the panel
started closed, clicked the bubble, and watched it reopen with the correct
content.

## Feature added, then found broken, then fixed twice more: stop generation

Added a "Stop generating" button per the user's request. Design: cooperative,
not a hard cancel — the backend checks a per-session stop flag between
tokens and, once set, finalizes through the exact same persistence path as a
natural completion (same citation/artifact detection, same
`_finalize()`/`StreamDone`), just with less text. Deliberately not
implemented via cancelling the request/task: that would mean performing an
async DB write from inside a cancellation handler, a genuine asyncio footgun
where a second cancellation can land mid-cleanup.

Reported live shortly after shipping it, with a screenshot: "stop generating
button is not working here" — mid-conversation, while the reply still said
"Ollama is thinking..." Root cause: the cooperative check only ran *after* a
token arrived, so a click during the "no token produced yet" phase (which for
Ollama's prompt processing can last many seconds) had nothing to interrupt —
a plain flag check between already-arrived tokens can't reach into a wait for
one that hasn't shown up. Fixed with `_stoppable`, a wrapper that races the
pending "get the next token" call against the stop signal via
`asyncio.wait(..., FIRST_COMPLETED)`, and — the part that took real care to
get right — only ever cancels that pending call when stop actually fires,
never on any kind of timeout or poll. That distinction matters: cancelling a
suspended async-generator frame closes it for good, so a generator can't be
safely "polled and resumed" by repeatedly cancelling and retrying; an earlier
design sketch using `asyncio.wait_for` in a retry loop would have silently
truncated any generation with a token gap longer than the poll interval,
which would have been a far worse bug than the one it fixed.

Writing the regression test for this caught a second, independent bug before
it ever reached the user: the stop-event registry entry was created *after*
an `await` on a database lookup, leaving a real window where a stop request
arriving in that gap would find nothing registered yet and silently no-op.
The test itself hit this race (a 5-second timeout tripped, cascading into an
`aclose(): asynchronous generator is already running` error) — not a flaky
test, an actual bug the test was right to catch. Fixed by registering the
stop event synchronously, as the literal first statement in the endpoint,
before any `await` at all — a client physically cannot issue a stop request
before this endpoint has started running, so this closes the window rather
than narrowing it. Ran the test suite five times in a row afterward to
confirm the fix was deterministic, not just lucky timing.

One more edge case, found while verifying: stopping before any token at all
was produced left an empty assistant message that had somehow still
"attached" every retrieved source as a citation — `_citations_from_text`'s
fallback for a model that ignores `[S1]`-style tags treats *no* tags as "cite
everything," which is reasonable for a real but tag-less reply and wrong for
a blank one. Fixed by returning no citations for empty text outright, and
gave the frontend a plain "Stopped before any response was generated."
placeholder instead of rendering a blank, broken-looking bubble.

Verified live end to end: clicked stop within ~0.3 seconds of sending, before
any token had arrived — resolved in 0.2–0.3 seconds (down from what would
have been an open-ended wait for the CPU-only generation), with the
placeholder text and no citations, exactly as intended.
