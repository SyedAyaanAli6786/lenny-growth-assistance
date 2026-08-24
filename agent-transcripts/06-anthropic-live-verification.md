# Session log — Live Anthropic API verification

The user provided a real Anthropic API key (asked to have it saved to `.env` —
done, confirmed it stays gitignored and was never committed). This closed the
loop on the `anthropic_provider.py` fixes from the source-verification session
(invalid `permission_mode`, missing `tools=[]`) — those were verified against
the SDK's source without a key; this was the first chance to verify runtime
behavior against the real API.

## What happened

`GET /health` correctly reported `anthropic: ok` once the key was set — that
check only confirms a key is present, not that it has usable credit, which
matters for what came next.

A real grounded chat message through `POST /api/sessions/{id}/messages` with
the provider switched to `anthropic` failed with `Command failed with exit
code 1`, the Claude Agent SDK's generic wrapper around a failed subprocess
call, with no further detail surfaced through the SDK's own error message.

Diagnosed by invoking the SDK's bundled CLI binary directly
(`claude_agent_sdk/_bundled/claude`) with the same API key, bypassing the SDK
wrapper to see the raw output: **"Credit balance is too low."** Not a code
bug — this is an Anthropic account/billing state, not something fixable in
this repo. The request reached Anthropic's servers and got back a specific,
well-formed billing rejection rather than an auth or malformed-request error,
which is itself informative: it confirms the `permission_mode="dontAsk"` /
`tools=[]` / `model="claude-sonnet-4-5"` configuration from the prior
source-verification session is well-formed enough to produce a valid request.

## Net result

The Anthropic path's request construction is now about as verified as it can
be without spending money: confirmed correct against the SDK's source
(previous session) and confirmed well-formed enough to reach Anthropic's API
and get a real, specific response (this session). What's still unverified is
the actual successful-response parsing path (`AssistantMessage`/`TextBlock`
handling in `anthropic_provider.py`'s `_run()` loop) — that needs a request
that actually succeeds, which needs account credit. Not pursuing that further
without the user's explicit choice to fund it — they were explicit up front
about not wanting to spend money, and got clear, useful signal (the code
seems right; it's a billing gate, not a bug) without needing to.
