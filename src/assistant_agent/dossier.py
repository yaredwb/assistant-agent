"""Dossier resolver: prefer a native dossier the coding agent already wrote; otherwise
synthesize one from git + transcripts (the fallback generator). Both paths return a
validated Dossier and are cached under <repo>/reviews/.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .collector import build_work_context
from .contract import Dossier, load_dossier, save_dossier


def reviews_dir(repo_path: Path) -> Path:
    return repo_path / "reviews"


def latest_path(repo_path: Path) -> Path:
    return reviews_dir(repo_path) / "latest.json"


def resolve_dossier(
    repo_name: str, repo_path: Path, *, force_generate: bool = False
) -> tuple[Dossier, str]:
    """Return (dossier, source) where source is 'native' or 'fallback'."""
    native = latest_path(repo_path)
    if native.exists() and not force_generate:
        try:
            return load_dossier(native), "native"
        except Exception:
            # Corrupt/incompatible native dossier — fall through to regenerate.
            pass

    from . import gemini_text  # imported lazily so non-voice/non-LLM paths don't need a key

    ctx = build_work_context(repo_name, repo_path)
    dossier = gemini_text.synthesize_dossier(ctx)

    # Cache: latest.json + a timestamped copy.
    save_dossier(dossier, native)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    save_dossier(dossier, reviews_dir(repo_path) / f"dossier-{stamp}.json")
    return dossier, "fallback"
