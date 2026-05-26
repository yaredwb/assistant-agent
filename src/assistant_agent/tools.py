"""Tools the voice agent can call mid-conversation. They *serve the walkthrough* —
fetching detail and recording feedback — not turn the voice agent into a coding agent.

`ToolBox` binds the tools to a specific repo + dossier and accumulates feedback. The
Live-API function declarations are derived from the same set.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .contract import Dossier
from . import feedback


class ToolBox:
    def __init__(self, repo_name: str, repo_path: Path, dossier: Dossier):
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.dossier = dossier
        self.feedback_items: list[str] = []

    # ---- conversation-serving read tools ----------------------------------

    def read_dossier(self) -> str:
        return self.dossier.model_dump_json(indent=2)

    def list_changed_files(self) -> str:
        return json.dumps(
            [
                {"path": f.path, "change_type": f.change_type, "summary": f.summary}
                for f in self.dossier.changed_files
            ],
            indent=2,
        )

    def show_diff(self, file: str) -> str:
        out = self._git("diff", "HEAD~5", "HEAD", "--", file) or self._git("diff", "--", file)
        return out[:8000] or f"No diff found for {file!r}."

    def read_file(self, path: str, start_line: int = 1, end_line: int = 200) -> str:
        target = (self.repo_path / path).resolve()
        if self.repo_path not in target.parents and target != self.repo_path:
            return "Refused: path is outside the repo."
        if not target.is_file():
            return f"No such file: {path}"
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        chunk = lines[max(0, start_line - 1) : end_line]
        return "\n".join(f"{i}\t{l}" for i, l in enumerate(chunk, start=max(1, start_line)))[:8000]

    def show_test_results(self) -> str:
        if self.dossier.tests_run:
            return "Tests recorded in the dossier:\n" + "\n".join(f"- {t}" for t in self.dossier.tests_run)
        return "No test results were recorded in the dossier for this work."

    # ---- feedback / handoff -----------------------------------------------

    def record_feedback(self, item: str) -> str:
        self.feedback_items.append(item)
        return f"Recorded feedback ({len(self.feedback_items)} so far): {item}"

    def create_followup_prompt_for_coding_agent(self) -> str:
        if not self.feedback_items:
            return "No feedback recorded yet, so there is nothing to hand off."
        prompt_file, command = feedback.create_followup_prompt(
            self.repo_path, self.repo_name, self.dossier, self.feedback_items
        )
        return f"Wrote follow-up prompt to {prompt_file}. Run it with:\n{command}"

    # ---- helpers -----------------------------------------------------------

    def _git(self, *args: str) -> str:
        try:
            return subprocess.run(
                ["git", "-C", str(self.repo_path), *args],
                capture_output=True, text=True, check=True, timeout=20,
            ).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return ""

    def dispatch(self, name: str, args: dict) -> str:
        """Route a Live-API function call to the matching method."""
        method = getattr(self, name, None)
        if method is None or name.startswith("_") or name == "dispatch":
            return f"Unknown tool: {name}"
        try:
            return str(method(**(args or {})))
        except TypeError as e:
            return f"Bad arguments for {name}: {e}"
        except Exception as e:  # tools must never crash the live session
            return f"Tool {name} failed: {e}"


# Function declarations advertised to the Live API.
FUNCTION_DECLARATIONS = [
    {"name": "read_dossier", "description": "Return the full review dossier as JSON."},
    {"name": "list_changed_files", "description": "List the changed files with one-line summaries."},
    {
        "name": "show_diff",
        "description": "Show the git diff for one file from the reviewed work.",
        "parameters": {
            "type": "object",
            "properties": {"file": {"type": "string", "description": "Repo-relative file path."}},
            "required": ["file"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a slice of a file's current contents.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repo-relative file path."},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
        },
    },
    {"name": "show_test_results", "description": "Report what tests/checks were run."},
    {
        "name": "record_feedback",
        "description": "Record a piece of the engineer's feedback or a requested change.",
        "parameters": {
            "type": "object",
            "properties": {"item": {"type": "string", "description": "The feedback or change request."}},
            "required": ["item"],
        },
    },
    {
        "name": "create_followup_prompt_for_coding_agent",
        "description": "Turn all recorded feedback into a runnable follow-up prompt for the coding agent.",
    },
]
