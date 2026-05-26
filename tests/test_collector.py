import json
import subprocess
from pathlib import Path

from assistant_agent import collector


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "-C", str(path), "add", "seed.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "seed"],
        check=True,
    )


def test_encoded_project_dirname():
    p = Path("/home/yaredwb/GeoSim.AI-JS")
    assert collector._encoded_project_dirname(p) == "-home-yaredwb-GeoSim-AI-JS"


def test_content_to_text_string():
    text, tools = collector._content_to_text("hello world")
    assert text == "hello world"
    assert tools == []


def test_content_to_text_blocks():
    content = [
        {"type": "text", "text": "let me edit"},
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/a/b.py"}},
        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}},
    ]
    text, tools = collector._content_to_text(content)
    assert text == "let me edit"
    assert tools[0].startswith("Edit(/a/b.py")
    assert tools[1].startswith("Bash(pytest")


def test_parse_ts():
    assert collector._parse_ts("2026-05-16T04:34:48.737Z").year == 2026
    assert collector._parse_ts(None) is None
    assert collector._parse_ts("not-a-date") is None


def test_collect_git_on_this_repo():
    # This repo is a real git repo with commits — exercise the real git path.
    repo = Path(__file__).resolve().parents[1]
    git = collector.collect_git(repo, max_commits=5)
    assert git.head  # non-empty sha
    assert git.branch  # e.g. 'main'
    assert isinstance(git.commits, list) and git.commits


# --- regression: Codex finding #1 (evidence must include staged + untracked work) -----


def test_collect_git_includes_untracked_only_change(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "newfile.py").write_text("print('hi')\nx = 1\n")
    git = collector.collect_git(tmp_path)
    by_path = {f["path"]: f for f in git.changed_files}
    assert "newfile.py" in by_path, "untracked file missing from changed_files"
    assert by_path["newfile.py"]["change_type"] == "added"
    assert "newfile.py" in git.untracked_files
    assert "print('hi')" in git.diff_excerpt  # concrete file evidence is present


def test_collect_git_includes_staged_only_change(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "staged.py").write_text("a = 2\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "staged.py"], check=True)
    git = collector.collect_git(tmp_path)
    by_path = {f["path"]: f for f in git.changed_files}
    assert "staged.py" in by_path, "staged file missing from changed_files"
    assert by_path["staged.py"]["change_type"] == "staged"


# --- regression: Codex finding #2 (transcript matching must fail closed) ---------------


def test_transcripts_fail_closed_on_missing_or_mismatched_cwd(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    other_project = projects / "-some-other-project"
    other_project.mkdir(parents=True)

    repo = (tmp_path / "myrepo").resolve()  # encoded dir absent -> broad fallback scan
    records = [
        # No cwd, from an unrelated project dir: must be skipped (the leak Codex flagged).
        {"type": "user", "message": {"role": "user", "content": "LEAKED no-cwd record"},
         "timestamp": "2099-01-01T00:00:00Z"},
        # cwd of a different repo: must be skipped.
        {"type": "user", "message": {"role": "user", "content": "OTHER repo record"},
         "cwd": "/somewhere/else", "timestamp": "2099-01-01T00:00:00Z"},
        # cwd matches our repo: must be kept.
        {"type": "user", "message": {"role": "user", "content": "MINE matching record"},
         "cwd": str(repo), "timestamp": "2099-01-01T00:00:00Z", "sessionId": "s1"},
    ]
    (other_project / "log.jsonl").write_text("\n".join(json.dumps(r) for r in records))
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))

    tctx = collector.collect_transcripts(repo)
    joined = " ".join(tctx.user_prompts)
    assert "MINE" in joined
    assert "LEAKED" not in joined
    assert "OTHER" not in joined
    assert tctx.session_ids == ["s1"]


def test_candidate_dirs_exact_match_is_trusted(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    repo = (tmp_path / "myrepo").resolve()
    encoded = projects / collector._encoded_project_dirname(repo)
    encoded.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))
    dirs = collector._candidate_transcript_dirs(repo)
    assert dirs == [(encoded, True)]
