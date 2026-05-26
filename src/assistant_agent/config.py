"""Configuration: env vars, repo registry, and shared paths."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # read .env from cwd / project root if present

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOS_TOML = PROJECT_ROOT / "repos.toml"

TEXT_MODEL = os.environ.get("ASSISTANT_TEXT_MODEL", "gemini-3-flash-preview")
VOICE_MODEL = os.environ.get(
    "ASSISTANT_VOICE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"
)


def claude_projects_dir() -> Path:
    return Path(
        os.path.expanduser(os.environ.get("CLAUDE_PROJECTS_DIR", "~/.claude/projects"))
    )


def api_key() -> str | None:
    """The google-genai SDK reads GEMINI_API_KEY (or GOOGLE_API_KEY) itself; this is
    only for a friendly upfront check."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


@dataclass(frozen=True)
class Repo:
    name: str
    path: Path

    @property
    def exists(self) -> bool:
        return (self.path / ".git").is_dir()


def load_registry() -> dict[str, Repo]:
    if not REPOS_TOML.exists():
        return {}
    data = tomllib.loads(REPOS_TOML.read_text(encoding="utf-8"))
    out: dict[str, Repo] = {}
    for name, cfg in data.get("repos", {}).items():
        out[name] = Repo(name=name, path=Path(os.path.expanduser(cfg["path"])).resolve())
    return out


def resolve_repo(name_or_path: str) -> Repo:
    """Resolve a registry name or a filesystem path to a Repo."""
    registry = load_registry()
    if name_or_path in registry:
        return registry[name_or_path]
    p = Path(os.path.expanduser(name_or_path)).resolve()
    if p.is_dir():
        # Use the directory name as the repo name.
        return Repo(name=p.name, path=p)
    raise ValueError(
        f"'{name_or_path}' is neither a registered repo name nor a directory. "
        f"Known repos: {', '.join(sorted(registry)) or '(none)'}"
    )
