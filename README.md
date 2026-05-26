# Assistant Agent

A voice-enabled colleague that walks you through completed AI coding work. Instead of
reading diffs across many repos, you run `assistant review <repo>` and it presents what
the coding agent did — by voice — answering your questions against the repo and capturing
your feedback as a follow-up task you can hand back to the coding agent.

See [`PLAN.md`](./PLAN.md) for the full design and roadmap.

## How it works

```
coding agent finishes work
        │
        ▼
review dossier  ── native (reviews/latest.json)  OR  fallback (generated from git + Claude Code transcripts)
        │
        ▼
assistant review <repo>  ──►  Gemini Live voice walkthrough  ──►  Q&A (repo tools)  ──►  feedback  ──►  follow-up prompt for coding agent
```

The **Review Artifact Contract** (`src/assistant_agent/contract.py`) is the linchpin: a
versioned schema any coding agent can emit and the voice agent consumes. If a repo has no
native `reviews/latest.json`, a fallback generator synthesizes one from git history + the
repo's Claude Code session transcripts.

## Setup

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
cp .env.example .env      # then add your GEMINI_API_KEY
```

Voice also needs the PortAudio system library and a working mic/speaker. On WSL/Ubuntu:

```bash
sudo apt-get install -y libportaudio2 libasound2-plugins
uv run assistant audio-check        # records 3s and plays it back
```

On WSLg, audio routes through the WSLg PulseAudio server (`/mnt/wslg/PulseServer`); your
Windows mic must be available. If PortAudio can't reach PulseAudio, the `soundcard`
library (libpulse-native) is a drop-in alternative for `audio.py`.

## Usage

```bash
uv run assistant list                 # registered repos (repos.toml) + review status
uv run assistant brief geosim         # resolve/generate a dossier and print it (no voice)
uv run assistant brief geosim --generate   # force fallback generation from git + transcripts
uv run assistant review geosim        # voice walkthrough (needs API key + audio)
```

`<repo>` is a name from `repos.toml` or a path to any git repo.

## Verification

```bash
uv run pytest -q                      # contract / collector / feedback unit tests
uv run assistant list                 # lists your repos
uv run assistant audio-check          # confirms mic/speaker before a voice session
uv run assistant brief geosim --generate   # exercises the fallback generator (needs key)
```

## Status (MVP)

Done: contract, collector (git + transcripts matched by `cwd`), fallback generator,
dossier resolver, voice walkthrough (Gemini Live), conversation tools, feedback capture +
follow-up handoff, CLI, shared-memory state.

Next (see `PLAN.md`): native dossier producer (Claude Code `Stop` hook), proactive
calendar scheduling, auto-apply feedback, multi-repo digest.
