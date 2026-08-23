# design.md — UI/UX

## Principles

1. **Trust over polish.** Every grounded claim is traceable to a source. Citations are never hidden behind a click the user has to know exists — a citation chip is visible inline as soon as an answer renders.
2. **The model is a visible, swappable component, not magic.** The active provider/model is always shown, never buried in a settings page the user has to hunt for.
3. **Artifacts live beside the conversation, not instead of it.** The brief explicitly calls out "beside the chat, not redirecting to another application" — the artifact panel is a persistent split, not a modal that hides the conversation.
4. **Fail loud, fail specific.** No spinners that never resolve, no generic "something went wrong." Every failure state names the failing component (Ollama, DB, retrieval) and what to do next.

## Information architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Top bar: app name · Provider Toggle (● Claude / ○ Ollama)    │
├───────────────┬─────────────────────────────┬────────────────┤
│ Session        │ Chat panel                   │ Artifact Viewer │
│ Sidebar        │  - Message list               │  (collapsed by  │
│  - New chat    │  - Citation chips per answer   │   default;      │
│  - Session list│  - Message input + Ship30 btn  │   opens when an │
│  - (per item:  │                               │   artifact      │
│    title,      │                               │   exists)       │
│    updated_at) │                               │  - Preview/Code │
│                │                               │    tabs         │
└───────────────┴─────────────────────────────┴────────────────┘
```

- **Session Sidebar** (collapsible on mobile): list of sessions by recency, "New chat" creates an independent session with its own context.
- **Chat panel**: the primary surface. Each assistant message that used retrieval shows a small "Sources (n)" expandable row under it, listing episode title + guest + link.
- **Artifact Viewer**: appears only once an artifact exists for the session; otherwise the chat panel takes the full remaining width. Tabs: **Preview** (rendered) and **Source** (raw markdown/HTML). A banner at the top of any HTML preview states "Sandboxed preview — scripts run, network and parent-page access are blocked" so the isolation strategy is visible to the user, not just documented in a file only engineers read.

## Key interaction states

| State | Behavior |
|---|---|
| Empty session | Chat panel shows a short prompt ("Ask about product, growth, retention...") with 2–3 example questions drawn from the vendored transcript topics. |
| Sending | Message input disables, a typing indicator with the active provider's name appears ("Ollama is thinking…"). |
| Streamed/returned answer | Message renders; citation row renders directly under it if sources were used; if no sources cleared the relevance threshold, the message visibly says so instead of a citation row. |
| Artifact produced | Artifact Viewer panel slides open (desktop) or becomes a bottom sheet (mobile); focus moves to the panel's heading for screen readers. |
| Ship 30 running | Message input shows a distinct "Drafting Ship 30 essay…" state (this call is slower — sets expectations rather than looking stuck). |
| Provider unavailable | Dropdown entry for that provider is visibly disabled with a tooltip reason ("Ollama not reachable" / "No Anthropic key configured"), sourced live from `/health`. |
| Retrieval/DB/model error | Inline error bubble in the message list, styled distinctly from a normal assistant message, naming the failing component and a retry action. |

## Responsive behavior

- **Desktop (≥1024px)**: three-column layout as above; artifact panel ~40% width, resizable-feeling via a fixed split (no drag-resize in v1 — noted as a future nicety).
- **Tablet (768–1023px)**: sidebar collapses to an icon rail; artifact panel becomes an overlay that pushes the chat panel to ~50%.
- **Mobile (<768px)**: single column; sidebar behind a hamburger; artifact opens as a full-height bottom sheet with a drag-down/close affordance, chat remains reachable via a close button (not lost).

## Accessibility

- All interactive controls (provider toggle, session list items, Ship 30 action, artifact tabs) are real buttons/links with visible focus rings, reachable by keyboard alone.
- New assistant messages append to an `aria-live="polite"` region so screen readers announce answers without interrupting typing.
- Artifact panel open moves focus to its heading; closing it returns focus to the triggering control.
- Color is never the only signal — the provider indicator and error states pair color with text/icon.
- Minimum body text contrast target: WCAG AA (4.5:1) in both light and dark themes.

## Provider toggle UX

A two-state segmented control in the top bar (Claude / Ollama), not a settings page — this is a first-class, evaluator-facing control since demonstrating the toggle live is part of the deliverable. Selecting a provider mid-session applies to the *next* message only; past messages keep a small badge noting which provider produced them, so a mixed-provider session stays legible.
