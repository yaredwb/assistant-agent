"""Command-line entry point.

    assistant list                 # registered repos + review status
    assistant brief <repo>         # resolve/generate a dossier and print it (no voice)
    assistant review <repo>        # voice walkthrough of the repo's recent work
    assistant audio-check          # verify mic/speaker before a voice session

`<repo>` is a name from repos.toml or a path to a git repo.
"""

from __future__ import annotations

import argparse
import sys

from . import config, state
from .dossier import resolve_dossier


def _cmd_list(_: argparse.Namespace) -> int:
    registry = config.load_registry()
    if not registry:
        print("No repos registered. Add some to repos.toml.")
        return 0
    for name, repo in sorted(registry.items()):
        st = state.get_repo_state(name)
        last = st.get("last_reviewed_at", "never")
        mark = "✓" if repo.exists else "✗ (not found)"
        print(f"{name:<14} {mark:<16} last reviewed: {last}  → {repo.path}")
    return 0


def _print_brief(dossier, source: str) -> None:
    print(f"\n=== Dossier for {dossier.repo} ({source}) ===")
    print(f"Task:    {dossier.task or '(unspecified)'}")
    print(f"Branch:  {dossier.branch}")
    print(f"\nSummary:\n  {dossier.summary}\n")

    def section(title, items, fmt=lambda x: x):
        if items:
            print(f"{title}:")
            for it in items:
                print(f"  - {fmt(it)}")
            print()

    section("Changed files", dossier.changed_files, lambda f: f"{f.path} — {f.summary}")
    section("Key decisions", dossier.key_decisions)
    section("Tests run", dossier.tests_run)
    section("Risks", dossier.risks)
    section("Open questions", dossier.open_questions)
    section("Walkthrough order", dossier.suggested_walkthrough_order)


def _resolve(args) -> tuple:
    repo = config.resolve_repo(args.repo)
    if not repo.exists:
        print(f"warning: {repo.path} is not a git repo (no .git).", file=sys.stderr)
    return repo, resolve_dossier(repo.name, repo.path, force_generate=args.generate)


def _cmd_brief(args: argparse.Namespace) -> int:
    repo, (dossier, source) = _resolve(args)
    _print_brief(dossier, source)
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    repo, (dossier, source) = _resolve(args)
    _print_brief(dossier, source)
    from .tools import ToolBox
    from . import voice

    toolbox = ToolBox(repo.name, repo.path, dossier)
    voice.review(toolbox)

    head = None
    if dossier.evidence.commits:
        head = dossier.evidence.commits[0]
    state.record_review(repo.name, dossier_path=str(repo.path / "reviews" / "latest.json"), commit=head)
    return 0


def _cmd_audio_check(_: argparse.Namespace) -> int:
    from scripts.audio_smoketest import main as audio_main  # type: ignore

    return audio_main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="assistant", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List registered repos and review status.").set_defaults(func=_cmd_list)

    p_brief = sub.add_parser("brief", help="Resolve/generate a dossier and print it.")
    p_brief.add_argument("repo")
    p_brief.add_argument("--generate", action="store_true", help="Force fallback generation.")
    p_brief.set_defaults(func=_cmd_brief)

    p_review = sub.add_parser("review", help="Voice walkthrough of a repo's recent work.")
    p_review.add_argument("repo")
    p_review.add_argument("--generate", action="store_true", help="Force fallback generation.")
    p_review.set_defaults(func=_cmd_review)

    sub.add_parser("audio-check", help="Verify mic/speaker.").set_defaults(func=_cmd_audio_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
