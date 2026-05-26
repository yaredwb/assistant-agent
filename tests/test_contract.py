import json

import pytest
from pydantic import ValidationError

from assistant_agent.contract import Dossier, load_dossier, save_dossier


def _valid_dict():
    return {
        "schema_version": "1",
        "repo": "demo",
        "branch": "main",
        "task": "Add a feature",
        "summary": "Did the thing.",
        "changed_files": [{"path": "src/x.py", "change_type": "modified", "summary": "tweak"}],
        "key_decisions": ["used approach A"],
        "tests_run": ["pytest"],
        "risks": ["edge case Y"],
        "open_questions": ["should we cache?"],
        "suggested_walkthrough_order": ["what", "why"],
        "evidence": {"commits": ["abc123"], "diff_refs": [], "transcript_refs": ["sess-1"]},
    }


def test_roundtrip(tmp_path):
    d = Dossier.model_validate(_valid_dict())
    p = save_dossier(d, tmp_path / "reviews" / "latest.json")
    assert p.exists()
    again = load_dossier(p)
    assert again.repo == "demo"
    assert again.changed_files[0].path == "src/x.py"
    assert again.evidence.transcript_refs == ["sess-1"]


def test_minimal_dossier_validates():
    # Only `repo` is required; everything else has a sensible default.
    d = Dossier.model_validate({"repo": "x"})
    assert d.schema_version == "1"
    assert d.changed_files == []
    assert d.evidence.commits == []


def test_missing_required_repo_rejected():
    bad = _valid_dict()
    del bad["repo"]
    with pytest.raises(ValidationError):
        Dossier.model_validate(bad)


def test_schema_json_is_generatable():
    # Used as the Interactions API response_format schema.
    schema = Dossier.model_json_schema()
    assert json.dumps(schema)  # serializable
    assert "repo" in schema["properties"]
