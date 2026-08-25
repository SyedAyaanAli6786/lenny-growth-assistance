# Demo video script (3 minutes)

## Filming note

CPU-only Ollama replies take 1-2 minutes each (measured, per `README.md`) — a
complete one cannot be shown in real time inside a 3-minute video. Record
each Ollama segment for real, then speed it up 6-10x in editing (or hard-cut
once ~5 seconds of visible streaming has played) so the viewer sees tokens
arriving without the runtime cost. The Claude/cloud segment is fast enough
to show live, unedited — use it to prove the toggle actually changes
providers, not just the label.

## Script

| Time | Say this | On screen |
|---|---|---|
| **0:00-0:12** | "This is the Lenny Growth Assistant. It answers questions using real episodes from Lenny's Podcast. You can switch between a local AI and a cloud AI, and turn any chat into a full essay." | Land on the empty chat screen, sidebar open, provider toggle visible top bar. Cut to the three suggested-question chips ("How should I think about activation for a PLG product?", etc.). |
| **0:12-0:28** | "Before it answers, the app searches the transcripts by itself — the AI never decides what to search. That keeps every answer consistent, no matter which model I'm using." | Quick cut to the architecture diagram in `README.md` (or `architecture.md`) — 2-3 seconds, just enough to register the shape, not to be read. |
| **0:28-0:55** | "Right now I'm using the free, local AI — no key, no internet account needed. I'll ask a real question." Type it, then: "You can see the answer come in word by word, and right below it, which episode it came from." | Click a suggestion chip or type "What separates good onboarding from great onboarding?" Show the "Ollama is thinking…" pending state, then a few real seconds of streaming text, then hard cut to the completed reply. Click the "N sources" pill open — show title, guest, relevance score, "listen ↗" link. |
| **0:55-1:12** | "And if the podcasts don't cover something, it just says so — it never makes up an answer to sound smart." | Ask an out-of-scope question (e.g. "What's the weather in Tokyo?"). Show the decline message and "No transcript sources supported this answer." |
| **1:12-1:35** | "Now I'll switch to Claude, a cloud AI — one click, no restart. I'll ask a follow-up question. Same accurate answer, same sources — just a different AI writing it." | Click the provider toggle → Claude. Ask a follow-up in the same session. Let this one stream live and finish on camera (it's fast) — this is the one real-time full generation. |
| **1:35-2:05** | "Now the Ship 30 skill. It writes a full essay, around 1,250 words, from the same real information. It even checks its own writing, and fixes it if something's off." | Click **Ship 30/30** next to the input. Show "Drafting Ship 30 essay… (Claude)", a few seconds of streaming into the message bubble, then cut to the finished essay opening as an artifact in the side panel — headings, bold takeaways visible. |
| **2:05-2:22** | "Every answer can be stopped halfway. I'll click stop, and you'll see it keeps whatever was already written instead of losing it." | Start a new message, click **Stop generating** a second or two in, show the "Stopped before any response was generated" placeholder land cleanly. |
| **2:22-2:35** | "And even after closing this essay, I can open it again anytime — it's saved, not gone." | Close the artifact panel, click back into the assistant bubble that produced it, show it reopen with the same content — pulled fresh from the database, not from memory. |
| **2:35-2:52** | "The whole app is covered by automated tests, and it tells you clearly if something's broken — like the database or one of the AI models — instead of just crashing." | Terminal: run `pytest`, let the green summary line land on screen (`45 passed`). Quick cut to `curl localhost:3400/health` output. |
| **2:52-3:00** | "All the details are in the project files. This is the Lenny Growth Assistant." | Cut back to the chat UI, or a title card with the repo name. |

**Total: ~180s.** If a bit over after editing, the safest trims are the
architecture-diagram cutaway (0:12-0:28) and the reopen-artifact beat
(2:22-2:35) — both reinforce points already made elsewhere, unlike the
decline-on-no-coverage moment, which is the strongest trust signal and
shouldn't get cut.
