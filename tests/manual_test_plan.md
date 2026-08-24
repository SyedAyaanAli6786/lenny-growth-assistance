# Manual test plan — UI flows

Automated tests (`backend/tests/`) cover the API/persistence/retrieval/validator
contract. This plan covers what only a human clicking through the UI can verify:
rendering, sandboxing behavior, and perceived failure states. Run after
`make up` (+ `make ingest` once) with the frontend at http://localhost:3500.

| # | Flow | Steps | Expected result |
|---|---|---|---|
| 1 | Empty state | Open the app fresh | Empty-state prompt with example questions shown; no error. |
| 2 | New session grounded Q&A | Click "New chat", ask "How should I think about activation for a PLG product?" | Assistant reply appears; a "Sources (n)" row is visible under it; expanding it lists real episode titles/guests. |
| 3 | Follow-up context | In the same session, ask "What about for a marketplace instead?" | Reply is coherent with the prior turn (doesn't re-explain from scratch); sidebar session stays the same. |
| 4 | No-coverage question | Ask something unrelated to product/growth (e.g. "What's the weather tomorrow?") | Assistant explicitly states the transcripts don't cover it; "No transcript sources supported this answer" shown, not a fabricated citation. |
| 5 | Provider switch (live) | Toggle the top-bar control from Ollama to Claude (with `ANTHROPIC_API_KEY` set) mid-session, ask another question | Next reply's provider badge shows "anthropic"; prior messages keep their original provider badge. |
| 6 | Provider unavailable | Unset `ANTHROPIC_API_KEY`, reload, try selecting Claude | Claude option is visibly disabled with a reachability/reason tooltip sourced from `/health`. |
| 7 | Ship 30/30 essay | Ask a grounded question, then click "Ship 30/30" | A markdown artifact opens beside the chat: ~1,250 words, headings, at least one bolded phrase, a clear takeaway, citation tags. |
| 8 | Markdown artifact | Ask "Write this up as a short doc" | Artifact panel opens in Preview tab with rendered markdown; Source tab shows raw text; no raw HTML executes from within the markdown. |
| 9 | HTML artifact + sandbox | Ask "Give me an HTML snippet for a landing page hero" | Artifact renders in the iframe; amber banner explains the sandbox policy. |
| 10 | Sandbox escape attempt | Ask for an HTML artifact whose script tries `fetch('https://example.com')`, `window.top.location`, and a `<form target="_top">` submit | None of the three succeed — no network tab entry for the fetch, no parent navigation, no form submission reaching the top window. Confirms the `srcdoc` + `sandbox="allow-scripts"` + injected CSP policy in `architecture.md`. |
| 11 | Ollama down | Stop the `ollama` container (`docker compose stop ollama`), send a message on the Ollama provider | Chat shows a specific inline error ("Ollama call failed…"), not a hang or stack trace; `/health` shows `ollama: down`. |
| 12 | DB down | Stop the `db` container, reload the app | `/health` shows `db: down`; API calls return a clear degraded-state error rather than crashing the frontend. |
| 13 | Responsive — mobile | Resize to <768px width | Sidebar collapses behind a hamburger; artifact viewer becomes a full-height sheet with a working close button; chat remains usable. |
| 14 | Keyboard-only pass | Tab through: new chat, session list, provider toggle, message input, Ship 30 button, artifact tabs, close button | Every control is reachable and operable via keyboard alone, with a visible focus ring at each stop. |
| 15 | Session isolation | Create two sessions, ask different questions in each | Each session's message history and provider selection stay independent; switching sessions doesn't leak messages between them. |
