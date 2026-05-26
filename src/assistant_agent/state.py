"""Shared memory for the single orchestrator: per-repo review history + preferences.

A small JSON store at ~/.assistant-agent/state.json. Intentionally simple; swap for
SQLite if it grows.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path.home() / ".assistant-agent"
STATE_FILE = STATE_DIR / "state.json"


def _load() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"repos": {}, "preferences": {}}


def _save(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_repo_state(repo_name: str) -> dict:
    return _load().get("repos", {}).get(repo_name, {})


def record_review(repo_name: str, *, dossier_path: str, commit: str | None) -> None:
    data = _load()
    repos = data.setdefault("repos", {})
    entry = repos.setdefault(repo_name, {})
    entry["last_reviewed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry["last_reviewed_commit"] = commit
    entry["last_dossier_path"] = dossier_path
    entry["review_count"] = entry.get("review_count", 0) + 1
    _save(data)


def get_preferences() -> dict:
    return _load().get("preferences", {})
