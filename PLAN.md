# Assistant Agent — voice-enabled review colleague

## Context

You run AI coding tools (Claude Code, Codex, Gemini, etc.) across ~15 repos. The models
now complete in an hour what used to take you a week, so the bottleneck has shifted from
*doing* the work to *understanding and trusting* what was done. You can't confidently
share or build on a project you haven't internalized.

The product is **not another report generator** — your coding agents can already emit
Markdown/HTML/JSON summaries. The product is a **voice-enabled colleague** that takes a
completed-work artifact and **walks you through it by voice** — like a coworker stopping
by your office after finishing a task — answers your questions against the repo, captures
your feedback, and hands follow-up work back to the coding agent. (This reframing came out
of a Codex adversarial review of the first draft; see "Design stance" below.)

### Decisions locked (from your answers)
- **Role:** Present completed AI work and capture feedback; generate follow-up tasks for the coding agent (full auto-apply is a later phase).
- **Topology:** One orchestrator with per-repo config/adapters + shared memory — **not** one agent per repo.
- **Voice stack:** **Gemini Live** (all-in-one realtime voice + reasoning).
- **First slice:** Straight to a **voice walkthrough of one repo's recent work**.

### Design stance (post-review)
- **The review dossier is an *input artifact*, not the core.** The core is the voice agent that consumes it.
- **One contract, two producers.** Define a standard dossier schema. *Primary* producer = the coding agent emits it on task completion. *Fallback* producer = a generator that synthesizes the **same schema** from git + Claude Code transcripts, so the agent works on your **existing** repos today — not only on future, dossier-aware work. This fallback is the demoted role of the original "collector."
- Tools serve the conversation; the MVP voice agent is **not** a second coding agent.

### Environment facts that shape the build
- `/home/yaredwb/assistant-agent` is now a git repo (branch `main`, seeded `PLAN.md`). Node 24, Python 3.12, `uv` available.
- Claude Code transcripts: `~/.claude/projects/<encoded-path>/*.jsonl`; each line carries `cwd`, `gitBranch`, `timestamp` → filter sessions by `cwd`, avoiding fragile path reconstruction. (Feeds the fallback generator.)
- Google Calendar/Gmail/Drive MCP servers already configured (need re-auth) — the calendar path for a later phase, not the MVP.
- `gemini-interactions-api` skill available for Gemini work; `mcp-builder`/`skill-creator` if we later expose this as an MCP server/skill.

## The Review Artifact Contract (the linchpin)

A versioned schema every coding agent can produce and the voice agent can consume, written
to `reviews/latest.json` (+ timestamped copies) in each repo. Evidence is referenced by
**pointer**, not embedded, so artifacts stay small and the voice agent's tools fetch detail
on demand.

```json
{
  "schema_version": "1",
  "repo": "...", "branch": "...", "task": "...",
  "summary": "...",
  "changed_files": [],
  "key_decisions": [],
  "tests_run": [],
  "risks": [],
  "open_questions": [],
  "suggested_walkthrough_order": [],
  "evidence": { "commits": [], "diff_refs": [], "transcript_refs": [] }
}
```

## MVP — `assistant review <repo>` (voice-first)

Language: **Python, `uv`-managed** — fastest path to a talking demo (mature Gemini Live
Python SDK + local-audio path; trivial git/transcript parsing).

Flow: **load/produce dossier → voice walkthrough → Q&A → capture feedback → emit follow-up.**

### 1. Dossier resolver — `src/dossier/`
- If `reviews/latest.json` exists and validates against the contract → use it.
- Else **fallback generator**: collect git diff + matching transcripts (filter by `cwd`, window by `timestamp`), and produce a contract-conformant dossier via Gemini text (`gemini-interactions-api` skill). Cache it to `reviews/`.
- Pydantic model = single source of truth for the schema; validate both paths against it.

### 2. Voice walkthrough — `src/voice/`
A **Gemini Live** session, system-prompted as "a colleague walking me through what you
did: present in `suggested_walkthrough_order` — what changed, why, key decisions, tests,
risks, open questions — and pause for questions." Local mic-in / speaker-out. Tools the
live model can call mid-conversation:
- `read_dossier()`, `list_changed_files()`, `show_diff(file)`, `read_file(path, lines)`, `show_test_results()`
- `record_feedback(item)` — capture asks as structured action items during the talk.
- `create_followup_prompt_for_coding_agent()` — turn feedback into a runnable handoff.

These **serve the walkthrough**; they do not make the voice agent a full coding agent.

### 3. Feedback → follow-up — `src/feedback/`
On session end: write action items to `reviews/<repo>/<date>.feedback.md` and emit a
ready-to-run **Claude Code handoff** (`claude -p` prompt scoped to the repo). MVP stops at
"generated"; auto-apply-and-report is a later phase.

### 4. State / shared memory — `src/state/`
Small JSON/SQLite store: per-repo last-reviewed dossier/commit, your preferences, review
history. This is the single-orchestrator topology's shared memory.

### 5. Orchestration / CLI — `src/cli.py`
- `assistant review <repo>` → resolve dossier → voice walkthrough.
- `assistant list` → repos + pending-review status.
- Config: `.env` (`GEMINI_API_KEY`), `repos.toml` registry of your repo paths.

## Reuse (don't rebuild)
- **`gemini-interactions-api` skill** — dossier synthesis (text) + Live voice. Verify Live API specifics (model id, audio formats, mid-stream tool-use) against it at build time.
- **Claude Code transcripts** (`~/.claude/projects/`) — fallback generator's "what & why" source; filter by `cwd`.
- **Claude Code headless** (`claude -p`) — the follow-up handoff.
- **Google Calendar/Gmail MCP** (configured) — later-phase scheduling.
- `mcp-builder`/`skill-creator` — if we expose the assistant as an MCP server or skill.

## Roadmap after MVP
- **Phase 2 — Native dossier producer:** a Claude Code `Stop` hook or `/review-dossier` skill that writes a first-hand `reviews/latest.json` on task completion (richer than the fallback). Equivalent wrappers for Codex/Gemini. Shifts the primary producer to the coding agent, as intended.
- **Phase 3 — Proactive "knock on the door" + calendar:** a watcher detects a fresh dossier, checks Google Calendar via the configured MCP, and pings for a now-session or books a review. *(Re-auth Calendar MCP.)*
- **Phase 4 — Auto-apply feedback:** run the follow-up as a `claude -p` job in the repo, then report back what changed.
- **Phase 5 — Multi-repo + surfaces:** cross-repo digest/prioritization; optional browser/WebRTC voice front-end + push notifications.

## Risks to confirm early
- **WSL2 audio (top risk):** local mic/speaker from WSL2 is often unreliable. Primary = Python local-audio terminal client; **fallback** = a locally-served browser WebRTC page (Gemini Live supports browser clients). Validate audio I/O *before* building the rest of the voice layer.
- **Gemini Live API churn:** confirm current model id, audio config, and mid-stream tool-calling support via the skill/docs.
- **Contract stability:** the schema must be stable/versioned enough for multiple agents to target; start at `schema_version: "1"` and treat changes as migrations.
- **Transcript volume:** logs reach multiple MB; the fallback generator must window by timestamp and summarize before sending to the model.

## Verification (end-to-end)
1. **Contract:** Pydantic model round-trips a hand-written `reviews/latest.json`; invalid samples are rejected.
2. **Dossier resolver:** with no `latest.json`, the fallback generator produces a valid dossier for `GeoSim.AI-JS` from git + transcripts (matched by `cwd`); with one present, it's used as-is.
3. **Audio smoke test:** confirm mic-in/speaker-out works in this WSL2 env before wiring Gemini Live (decides terminal vs browser front-end).
4. **Voice:** `assistant review GeoSim.AI-JS` → it walks the dossier in order, answers a drill-down question (triggers `show_diff`/`read_file`), and records a feedback item.
5. **Follow-up:** confirm `reviews/<repo>/<date>.feedback.md` + a runnable `claude -p` handoff are produced.
