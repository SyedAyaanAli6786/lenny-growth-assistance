# Session log — Verifying the Claude Agent SDK integration against its source, without an API key

The user doesn't have budget for an Anthropic API key (they'd downloaded a local
model instead, precisely so I wouldn't need one). Rather than leave the Anthropic
provider's correctness as an open question until someone eventually pays for a
key, read the installed SDK's own source directly — no network call, no key,
no cost — since the package was already sitting in `backend/.venv`.

## What was wrong, confirmed by source, not guessed

`grep`-ed `permission_mode`/`PermissionMode` across
`claude_agent_sdk/types.py` and found:

```python
PermissionMode = Literal["default", "acceptEdits", "plan", "bypassPermissions", "dontAsk", "auto"]
```

`"deny"` — what `anthropic_provider.py` had been passing — was never a valid
value. It was an unverified guess from an earlier session (no API key was
available then either), flagged at the time as the most likely place the cloud
path would actually break, and now confirmed as exactly that.

Reading `ClaudeAgentOptions`'s full field list turned up a second, more
consequential gap: there are two different fields governing tool access.
`tools` — "Specify the base set of available built-in tools... `[]` disables
all built-in tools" — is what actually controls whether tools exist at all.
`allowed_tools` — what the code had set to `[]` — only controls which
*already-offered* tools skip a permission prompt; per its own docstring, "To
restrict which tools are available at all, use `tools` instead." The original
code's comment claimed "no filesystem/bash/network tools" based on
`allowed_tools=[]` alone, which doesn't actually make that claim true — `tools`
was left unset (`None`), an ambiguous default the docstring doesn't fully
pin down.

## Fixes applied

`backend/app/agent/anthropic_provider.py`:
- `tools=[]` — actually disables built-in tools from being offered, not just
  auto-approved.
- `permission_mode="dontAsk"` (not `"deny"`) — a real value whose documented
  semantics ("don't prompt; deny if not pre-approved") match the original
  intent exactly.
- `max_turns=1` — added as defense in depth, capping the call to a single
  generation turn regardless of the above.

Also fixed a stale doc claim in `architecture.md`: it said the Anthropic path
uses `ClaudeSDKClient`, but the code has only ever used the `query()` function
— corrected, and expanded to name the actual tool-restriction mechanism.

## What's still not verified

The fix compiles and `ClaudeAgentOptions(...)` constructs without error locally
(checked directly, no key needed for construction). What's still unverified is
runtime behavior against the real Anthropic API — whether `query()` actually
returns a normal `AssistantMessage`/`TextBlock` stream under this configuration,
and whether `max_turns=1` interacts correctly with a single-turn generation
call. That needs a real API key to confirm; everything checkable without one
has been checked.
