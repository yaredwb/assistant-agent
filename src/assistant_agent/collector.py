"""Collect raw 'what the AI did' context for a repo: git history + Claude Code
transcripts. Output feeds the fallback dossier generator.

Transcripts are matched by reading each JSONL line's `cwd` field (robust), but we
first narrow to the likely project directory by Claude Code's path-encoding scheme
(replace '/' and '.' with '-') to avoid scanning every project's multi-MB logs.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config


# --------------------------------------------------------------------------- git


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


@dataclass
class GitContext:
    branch: str = ""
    head: str = ""
    commits: list[dict] = field(default_factory=list)  # {sha, subject, date}
    changed_files: list[dict] = field(default_factory=list)  # {path, additions, deletions, change_type}
    untracked_files: list[str] = field(default_factory=list)
    diffstat: str = ""
    diff_excerpt: str = ""


def _count_lines(path: Path) -> int | None:
    try:
        with path.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return None


def _merge_numstat(numstat: str, change_type: str, into: dict[str, dict]) -> None:
    for line in numstat.splitlines():
        cols = line.split("\t")
        if len(cols) == 3:
            adds = None if cols[0] == "-" else int(cols[0])
            dels = None if cols[1] == "-" else int(cols[1])
            into[cols[2]] = {
                "path": cols[2],
                "additions": adds,
                "deletions": dels,
                "change_type": change_type,
            }


def collect_git(repo: Path, *, max_commits: int = 20, diff_char_budget: int = 12000) -> GitContext:
    """Capture the full picture of recent work: the committed window AND the current
    working tree (staged, unstaged, and untracked). Untracked-only changes — the common
    case before the work is committed — must show up with concrete file evidence."""
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = _git(repo, "rev-parse", "HEAD").strip()

    commits: list[dict] = []
    log = _git(repo, "log", f"-{max_commits}", "--pretty=format:%H%x1f%s%x1f%cI")
    for line in log.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            commits.append({"sha": parts[0], "subject": parts[1], "date": parts[2]})

    base = f"{head}~{min(max_commits, len(commits))}" if len(commits) > 1 else None

    # Merge changed files from every source. Later sources win on counts (working state
    # is more current than an older committed delta).
    files: dict[str, dict] = {}
    if base:
        _merge_numstat(_git(repo, "diff", "--numstat", base, head), "committed", files)
    _merge_numstat(_git(repo, "diff", "--cached", "--numstat"), "staged", files)
    _merge_numstat(_git(repo, "diff", "--numstat"), "modified", files)

    untracked = [f for f in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines() if f]
    for f in untracked:
        files.setdefault(
            f, {"path": f, "additions": _count_lines(repo / f), "deletions": 0, "change_type": "added"}
        )

    # diffstat: committed window + working tree (staged+unstaged) + untracked listing.
    stat_parts: list[str] = []
    if base:
        committed_stat = _git(repo, "diff", "--stat", base, head)
        if committed_stat.strip():
            stat_parts.append("# committed (recent window)\n" + committed_stat)
    if head:
        working_stat = _git(repo, "diff", "--stat", "HEAD")
        if working_stat.strip():
            stat_parts.append("# working tree (staged + unstaged)\n" + working_stat)
    if untracked:
        stat_parts.append("# untracked\n" + "\n".join(untracked))
    diffstat = "\n\n".join(stat_parts)

    # diff_excerpt: committed diff, then working-tree diff, then untracked file contents,
    # all within one shared char budget.
    budget = diff_char_budget
    chunks: list[str] = []

    def _take(text: str) -> None:
        nonlocal budget
        if budget > 0 and text:
            piece = text[:budget]
            chunks.append(piece)
            budget -= len(piece)

    if base:
        _take(_git(repo, "diff", base, head))
    if head:
        _take(_git(repo, "diff", "HEAD"))
    for f in untracked:
        if budget <= 0:
            break
        try:
            content = (repo / f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _take(f"\n--- new file: {f} ---\n{content}")

    return GitContext(
        branch=branch,
        head=head,
        commits=commits,
        changed_files=list(files.values()),
        untracked_files=untracked,
        diffstat=diffstat,
        diff_excerpt="".join(chunks),
    )


# --------------------------------------------------------------------- transcripts


def _encoded_project_dirname(repo: Path) -> str:
    # Claude Code encodes e.g. /home/yaredwb/GeoSim.AI-JS -> -home-yaredwb-GeoSim-AI-JS
    return re.sub(r"[/.]", "-", str(repo))


def _candidate_transcript_dirs(repo: Path) -> list[tuple[Path, bool]]:
    """Return (dir, is_exact). is_exact is True only for the repo's own encoded project
    directory; the broad fallback scan is marked False so we can fail closed there."""
    base = config.claude_projects_dir()
    if not base.is_dir():
        return []
    encoded = base / _encoded_project_dirname(repo)
    if encoded.is_dir():
        return [(encoded, True)]
    return [(d, False) for d in base.iterdir() if d.is_dir()]


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _content_to_text(content) -> tuple[str, list[str]]:
    """Return (text, tool_actions) from a message 'content' field."""
    if isinstance(content, str):
        return content, []
    texts: list[str] = []
    tools: list[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                texts.append(block["text"])
            elif btype == "tool_use":
                name = block.get("name", "tool")
                inp = block.get("input", {}) or {}
                target = inp.get("file_path") or inp.get("path") or inp.get("command") or ""
                tools.append(f"{name}({str(target)[:80]})" if target else name)
    return "\n".join(texts), tools


@dataclass
class TranscriptContext:
    session_ids: list[str] = field(default_factory=list)
    user_prompts: list[str] = field(default_factory=list)
    assistant_notes: list[str] = field(default_factory=list)
    tool_actions: list[str] = field(default_factory=list)


def collect_transcripts(
    repo: Path,
    *,
    since: datetime | None = None,
    days: int = 14,
    char_budget: int = 16000,
) -> TranscriptContext:
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(days=days)
    repo_str = str(repo)

    ctx = TranscriptContext()
    budget = char_budget
    for d, is_exact in _candidate_transcript_dirs(repo):
        for jsonl in sorted(d.glob("*.jsonl")):
            for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
                if budget <= 0:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Fail closed: only accept records whose cwd matches this repo exactly.
                # A missing cwd is trusted only inside the repo's own encoded dir.
                cwd = rec.get("cwd")
                if cwd is not None:
                    if cwd != repo_str:
                        continue
                elif not is_exact:
                    continue
                ts = _parse_ts(rec.get("timestamp"))
                if ts and ts < since:
                    continue
                sid = rec.get("sessionId")
                if sid and sid not in ctx.session_ids:
                    ctx.session_ids.append(sid)

                rtype = rec.get("type")
                msg = rec.get("message") or {}
                if rtype == "user":
                    text, _ = _content_to_text(msg.get("content"))
                    text = text.strip()
                    if text and not text.startswith("<"):  # skip tool-result / system noise
                        ctx.user_prompts.append(text[:1000])
                        budget -= len(text[:1000])
                elif rtype == "assistant":
                    text, tools = _content_to_text(msg.get("content"))
                    if text.strip():
                        ctx.assistant_notes.append(text.strip()[:1000])
                        budget -= len(text.strip()[:1000])
                    ctx.tool_actions.extend(tools)
    return ctx


# ------------------------------------------------------------------- combined ctx


@dataclass
class WorkContext:
    repo_name: str
    repo_path: str
    git: GitContext
    transcripts: TranscriptContext

    def to_prompt_dict(self) -> dict:
        """Compact, model-friendly view of the gathered context."""
        return {
            "repo": self.repo_name,
            "branch": self.git.branch,
            "recent_commits": [f"{c['sha'][:8]} {c['subject']}" for c in self.git.commits],
            "changed_files": self.git.changed_files,
            "untracked_files": self.git.untracked_files,
            "diffstat": self.git.diffstat,
            "diff_excerpt": self.git.diff_excerpt,
            "session_ids": self.transcripts.session_ids,
            "user_prompts": self.transcripts.user_prompts,
            "assistant_notes": self.transcripts.assistant_notes,
            "tool_actions": self.transcripts.tool_actions[:120],
        }


def build_work_context(repo_name: str, repo_path: Path, **kw) -> WorkContext:
    return WorkContext(
        repo_name=repo_name,
        repo_path=str(repo_path),
        git=collect_git(repo_path),
        transcripts=collect_transcripts(repo_path, **kw),
    )
