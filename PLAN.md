# Assistant Agent — AI work-review companion

## Context

You run AI coding tools (Claude Code, Codex, etc.) across ~15 repos. The models now
complete in an hour what used to take you a week, so the bottleneck has shifted from
*doing* the work to *understanding and trusting* what was done. You can't confidently
share or build on a project you haven't internalized.

The idea: an AI assistant that behaves like a human colleague who finished a task —
it prepares a walkthrough of what was done, **finds time on your calendar**, then
**sits down and walks you through it by voice**, answering questions and taking your
feedback so it can be applied. This plan builds that, starting with the part that
proves the whole concept: a live voice walkthrough of one repo's recent work.

### Decisions locked (from your answers)
- **Role:** Review & present recent AI work, **and** apply feedback (hand off to Claude Code under the hood).
- **Topology:** One orchestrator agent with per-repo adapters + shared memory (not one agent per repo).
- **Voice stack:** **Gemini Live** (all-in-one realtime voice + reasoning).
- **First slice:** Straight to a **voice walkthrough of one repo's recent work**.

### Environment facts that shape the build
- `/home/yaredwb/assistant-agent` is empty (greenfield). Node 24, Python 3.12, `uv` available.
- Claude Code transcripts live at `~/.claude/projects/<encoded-path>/*.jsonl`; each line carries `cwd`, `gitBranch`, `timestamp` → the collector can **filter sessions by reading `cwd`**, avoiding fragile path-name reconstruction.
- Google **Calendar/Gmail/Drive MCP servers are already configured** (need re-auth) — that's the calendar path for Phase 2, no new integration to build.
- `gemini-interactions-api` skill is available for the Gemini work; `mcp-builder` / `skill-creator` local if we later expose this as an MCP server/skill.

## MVP — voice walkthrough of one repo (`assistant review <repo>`)

Language: **Python, `uv`-managed.** Fastest path to a talking demo (Gemini Live has a
mature Python SDK + local-audio path; git/transcript parsing is trivial in Python).

Pipeline: **collect → brief → talk → capture feedback.**

### 1. Context collector — `src/collector/`
For a target repo, build a structured `WorkContext`:
- **Git:** branch, `git log` + `git diff` over a window (since last-reviewed commit/marker, else last N commits + working-tree changes), changed-file list.
- **Transcripts:** glob `~/.claude/projects/*/*.jsonl`, keep lines whose `cwd` matches the repo path and `timestamp` is in-window; extract user prompts, assistant summary text, and tool actions (files edited, commands run). Window/trim aggressively — single logs reach multiple MB.

### 2. Briefing builder — `src/briefing/`
Feed `WorkContext` to Gemini (text, via `gemini-interactions-api` skill) → a structured
`Briefing`: title, one-paragraph summary, themed change groups (*what* + *why*),
risks / things-to-verify, open questions, suggested walkthrough order. Cache to
`reviews/<repo>/<date>.briefing.json`. This is "the presentation the colleague prepared."

### 3. Voice walkthrough — `src/voice/`
A **Gemini Live** session that presents the `Briefing` conversationally and answers
drill-down questions. System-prompted as "a colleague walking me through what you did;
present in order, pause for questions, be concrete." Local mic-in / speaker-out.
Function-calling tools the live model can invoke on demand:
- `list_changes()`, `get_diff(file)`, `read_file(path, line_range)`, `get_session_excerpt(topic)` — pull detail beyond the briefing.
- `record_feedback(item)` — capture your asks as structured action items mid-conversation.

### 4. Feedback → action — `src/feedback/`
On session end: write action items to `reviews/<repo>/<date>.feedback.md` and generate a
ready-to-run **Claude Code handoff prompt** (`claude -p` invocation scoped to that repo).
MVP stops at "generated + optionally invoked"; fully automatic apply-and-report is Phase 3.

### 5. State / shared memory — `src/state/`
Small JSON (or SQLite) store: per-repo last-reviewed commit/timestamp, your preferences,
review history. This is the single-agent topology's shared memory.

### 6. Orchestration / CLI — `src/cli.py`
- `assistant review <repo>` → collect → brief → voice walkthrough.
- `assistant list` → repos + pending-review status.
- Config: `.env` (`GEMINI_API_KEY`), `repos.toml` registry of your ~15 repo paths.

## Reuse (don't rebuild)
- **`gemini-interactions-api` skill** — Gemini text briefing + Live voice. Verify Live API specifics (model id, audio formats, tool-use-in-Live) against it at build time.
- **Claude Code transcripts** (`~/.claude/projects/`) — primary "what did the AI do & why" source; filter by the `cwd` field.
- **Google Calendar/Gmail MCP** (already configured) — Phase 2 scheduling.
- **Claude Code headless** (`claude -p`) — the "apply feedback" handoff.
- `mcp-builder` / `skill-creator` — if we later expose the assistant itself as an MCP server or skill.

## Roadmap after MVP
- **Phase 2 — Proactive "knock on the door":** a watcher (Claude Code `Stop` hook or `/loop`/cron) detects significant new work in a repo, checks Google Calendar via the configured MCP, and either pings for a now-session or books a review meeting. *(Re-auth Calendar MCP.)*
- **Phase 3 — Auto-apply feedback:** convert recorded action items into Claude Code headless runs in the repo, then report back what changed (fulfills the "apply feedback" role end-to-end).
- **Phase 4 — Multi-repo orchestration:** orchestrator scans all repos, prioritizes which need review, presents a cross-repo digest; per-repo adapters handle language/test specifics.
- **Phase 5 — Surfaces:** optional browser/WebRTC voice front-end + push notifications.

## Risks to confirm early
- **WSL2 audio (top risk):** local mic/speaker from WSL2 is often unreliable. Primary path = Python local-audio terminal client; **fallback** = a minimal locally-served browser WebRTC page (Gemini Live supports browser clients). Validate audio I/O before building the rest of the voice layer.
- **Gemini Live API churn:** realtime APIs move fast — confirm current model id, audio config, and whether tool-calling is supported mid-stream via the skill/docs.
- **Transcript volume:** logs are multi-MB; the collector must window by timestamp and summarize before sending to the briefing model.

## Verification (end-to-end)
1. **Collector:** unit-test that `WorkContext` for `GeoSim.AI-JS` pulls the right diff window and matches transcript sessions by `cwd`.
2. **Briefing:** `assistant brief GeoSim.AI-JS` → eyeball the structured briefing for accuracy.
3. **Audio smoke test:** confirm mic-in/speaker-out works in this WSL2 env before wiring Gemini Live (decide terminal vs browser front-end based on result).
4. **Voice:** `assistant review GeoSim.AI-JS` → talk to it; confirm it walks recent work in order, answers a drill-down question (triggers a tool call), and records a feedback item.
5. **Feedback:** confirm `reviews/<repo>/<date>.feedback.md` + a runnable `claude -p` handoff prompt are produced.
