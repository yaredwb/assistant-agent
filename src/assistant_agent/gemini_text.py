"""Synthesize a contract-conformant Dossier from raw work context using the Gemini
Interactions API with structured (schema-constrained) output."""

from __future__ import annotations

import json

from google import genai

from . import config
from .collector import WorkContext
from .contract import Dossier

_SYSTEM = """You are a meticulous engineering reviewer. You are given the raw record of \
work an AI coding agent did in a repository: recent git commits, a diff excerpt, the \
list of changed files, and excerpts of the human's prompts and the agent's notes/tool \
actions from the coding session.

Produce a review dossier that a *voice assistant* will use to walk a busy engineer \
through what was done, as if a colleague were presenting it. Be concrete and specific \
to THIS work — no generic filler. Ground every claim in the provided evidence.

Fill the schema:
- task: what the agent was asked to do (infer from the prompts).
- summary: one tight paragraph a non-author can understand.
- changed_files: the meaningful ones, each with a one-line 'why it changed'.
- key_decisions: real choices/tradeoffs visible in the work.
- tests_run: any tests/checks evident in the session; empty if none.
- risks: things the reviewer should be wary of.
- open_questions: things genuinely unresolved or worth the engineer's judgment.
- suggested_walkthrough_order: the order to present topics in the meeting.
- evidence.commits / diff_refs / transcript_refs: point back to the source material."""


def _output_text(interaction) -> str:
    """The Interactions API exposes the result as `output_text`; older/alt builds use
    `outputs[-1].text`. Tolerate both."""
    text = getattr(interaction, "output_text", None)
    if text:
        return text
    outputs = getattr(interaction, "outputs", None) or []
    for block in reversed(outputs):
        if getattr(block, "text", None):
            return block.text
    raise ValueError("No text output found in interaction response.")


def synthesize_dossier(ctx: WorkContext) -> Dossier:
    if not config.api_key():
        raise RuntimeError(
            "No GEMINI_API_KEY (or GOOGLE_API_KEY) set. Add it to .env to generate a "
            "dossier. (A repo with a native reviews/latest.json needs no key.)"
        )
    client = genai.Client()  # reads GEMINI_API_KEY / GOOGLE_API_KEY
    payload = json.dumps(ctx.to_prompt_dict(), indent=2, default=str)

    interaction = client.interactions.create(
        model=config.TEXT_MODEL,
        system_instruction=_SYSTEM,
        input=f"Raw work context (JSON):\n\n{payload}",
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": Dossier.model_json_schema(),
        },
    )

    dossier = Dossier.model_validate_json(_output_text(interaction))
    # Trust our own collected provenance over whatever the model echoed.
    dossier.repo = ctx.repo_name
    dossier.branch = dossier.branch or ctx.git.branch
    if not dossier.evidence.commits:
        dossier.evidence.commits = [c["sha"] for c in ctx.git.commits]
    if not dossier.evidence.transcript_refs:
        dossier.evidence.transcript_refs = ctx.transcripts.session_ids
    return dossier.stamp("fallback-generator")
