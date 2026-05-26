"""The Review Artifact Contract.

A versioned schema every coding agent can produce and the voice agent consumes.
Evidence is referenced by *pointer* (commit shas, diff refs, transcript ids) so the
artifact stays small and the voice agent's tools fetch detail on demand.

This Pydantic model is the single source of truth for the schema — both the
fallback generator and any native producer (a Claude Code hook, etc.) must validate
against it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1"


class ChangedFile(BaseModel):
    path: str
    change_type: str = Field(
        default="modified", description="added | modified | deleted | renamed"
    )
    summary: str = Field(default="", description="One line on what changed and why.")
    additions: int | None = None
    deletions: int | None = None


class Evidence(BaseModel):
    """Pointers, not content."""

    commits: list[str] = Field(default_factory=list, description="Commit shas.")
    diff_refs: list[str] = Field(
        default_factory=list, description="e.g. 'HEAD~3..HEAD' or 'file:src/x.py'."
    )
    transcript_refs: list[str] = Field(
        default_factory=list,
        description="Claude Code session ids that produced this work.",
    )


class Dossier(BaseModel):
    schema_version: str = SCHEMA_VERSION
    repo: str = Field(description="Repo name or path.")
    branch: str = ""
    task: str = Field(default="", description="What the coding agent was asked to do.")
    summary: str = Field(default="", description="One-paragraph plain-language summary.")
    changed_files: list[ChangedFile] = Field(default_factory=list)
    key_decisions: list[str] = Field(default_factory=list)
    tests_run: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    suggested_walkthrough_order: list[str] = Field(
        default_factory=list,
        description="Ordered topics the voice agent should present.",
    )
    evidence: Evidence = Field(default_factory=Evidence)

    # Provenance (not part of the cross-agent contract, but useful locally).
    generated_by: str = Field(
        default="unknown",
        description="'coding-agent' | 'fallback-generator' | 'unknown'",
    )
    generated_at: str = ""

    def stamp(self, by: str) -> "Dossier":
        self.generated_by = by
        self.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return self


def load_dossier(path: str | Path) -> Dossier:
    """Load and validate a dossier from a JSON file. Raises on invalid."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Dossier.model_validate(data)


def save_dossier(dossier: Dossier, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dossier.model_dump_json(indent=2), encoding="utf-8")
    return path
