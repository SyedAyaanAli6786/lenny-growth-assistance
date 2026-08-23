# Vendored transcript subset

36 episode transcripts vendored from [`ChatPRD/lennys-podcast-transcripts`](https://github.com/ChatPRD/lennys-podcast-transcripts) — the transcript repository the assignment itself links to — selected for topic coverage (growth, activation, pricing, retention, positioning, GTM, PM leadership, AI-native building) and substantial length (20+ minute episodes only).

Each file has YAML frontmatter (`title`, `guest`, `url`, `date`) followed by the transcript body, with the source repo's per-second timestamp codes stripped for cleaner chunking while keeping speaker attribution (`Lenny:` / `<Guest name>:`).

This is intentionally a subset, not the full 269-episode archive (see PRD "Scope choices") — `scripts/ingest.py` works unmodified against the full archive if you drop more files in here.

**Usage**: educational/research use for this take-home assignment, per the source repository's own usage terms — "this archive is for educational and research purposes. All content belongs to Lenny's Podcast and the respective guests."
