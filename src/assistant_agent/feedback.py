"""Capture feedback from a walkthrough and emit a runnable follow-up handoff for the
coding agent (Claude Code headless). The MVP stops at *generating* the handoff; running
it is a later phase.
"""

from __future__ import annotations

import shlex
from datetime import datetime, timezone
from pathlib import Path

from .contract import Dossier
from .dossier import reviews_dir


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_feedback(repo_path: Path, repo_name: str, items: list[str]) -> Path:
    """Persist the engineer's feedback items as markdown."""
    out = reviews_dir(repo_path) / f"{_now_stamp()}.feedback.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Review feedback — {repo_name}", "", f"_Captured {datetime.now(timezone.utc).isoformat(timespec='seconds')}_", ""]
    lines += [f"- {item}" for item in items] or ["- (no feedback captured)"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def create_followup_prompt(
    repo_path: Path, repo_name: str, dossier: Dossier, items: list[str]
) -> tuple[Path, str]:
    """Build a Claude Code handoff prompt from feedback and write it to disk.

    Returns (prompt_file, shell_command) — the command the engineer (or a later phase)
    can run to apply the feedback.
    """
    bullet = "\n".join(f"- {item}" for item in items) or "- (no specific items)"
    prompt = f"""You are picking up follow-up work on **{repo_name}** after a review of \
recent changes.

Context — what was reviewed (task): {dossier.task or 'see reviews/latest.json'}
Summary: {dossier.summary}

The reviewer asked for the following follow-ups:
{bullet}

Implement these changes. Keep them scoped to the requests above. When done, update \
reviews/latest.json describing what you changed.
"""
    prompt_file = reviews_dir(repo_path) / f"{_now_stamp()}.followup.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")

    # Quote every path so spaces / shell metacharacters in the paths can't break or
    # alter the command the engineer copies.
    command = f"cd {shlex.quote(str(repo_path))} && claude -p \"$(cat {shlex.quote(str(prompt_file))})\""
    return prompt_file, command
