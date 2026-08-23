# Session log — Planning phase

**Date:** 2026-08-24
**Tool:** Claude Code (Sonnet 5)

## What was asked

User provided `Forward_Deployed_Engineer_Take_Home_Assignment.docx` and asked to build "The Lenny Growth Assistant" following the order the assignment document lays things out in.

## What I did

1. The docx couldn't be read directly (binary file, no `python-docx`/`pandoc` available in the environment). Unzipped it as a `.docx`/OOXML archive and stripped `word/document.xml` down to plain text with a small regex-based script instead of installing new tooling.
2. Read the full assignment text. Confirmed scope: FastAPI backend, Claude Agent SDK or Pi Coding Agent, PostgreSQL persistence, a cloud+local(Ollama) model toggle, RAG over Lenny's Podcast transcripts, a Ship 30 for 30 essay skill, an artifact viewer with HTML sandboxing, and a full FDE handoff doc set (PRD, design.md, architecture.md, README, tests, agent transcripts, demo video).
3. Extracted the hyperlink targets embedded in the docx (`word/_rels/document.xml.rels`) rather than guessing at URLs — this surfaced the assignment's *own* linked sources for "Lenny's Podcast transcript repository" (`github.com/ChatPRD/lennys-podcast-transcripts`) and the "Ship 30 for 30 guide" (ship30for30.com's writing guide), instead of picking an arbitrary transcript dataset or writing style guide from general knowledge.
4. Fetched both linked pages plus the Claude Agent SDK quickstart to ground technical decisions in the actual referenced material rather than assumptions.

## Decision / trade-off surfaced early

The brief requires (a) the agent layer to use the Claude Agent SDK, and (b) the whole thing to run locally via Ollama, switchable without code changes. The Agent SDK is Claude-only — it can't target Ollama. Rather than silently picking one requirement over the other, I flagged this in the plan and resolved it by making retrieval a deterministic server-side step (not a model-decided tool call), so the same grounded-answer behavior holds regardless of which provider executes the generation turn. The Claude Agent SDK drives the cloud path; a small parallel `OllamaProvider` with the identical interface drives the local path. This gets documented as a named risk/trade-off in the PRD rather than hidden.

## Clarifications asked of the user

- GitHub repo handling → build locally only, user will push themselves.
- Local Ollama availability/RAM → not installed, unsure of RAM → defaulting to a broadly safe model choice, documented and swappable via `.env`.
- Anthropic API key → user will add their own to `.env`; local Ollama path must work with zero keys.

## Next

Proceeding through the approved build order: repo scaffolding → PRD → design.md → architecture.md → backend scaffolding → LLM config layer → ingestion → conversational assistant → Ship 30/30 skill → artifact viewer → frontend → deployment/ops → tests → README.
