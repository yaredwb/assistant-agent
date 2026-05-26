from assistant_agent import feedback
from assistant_agent.contract import Dossier


def test_write_feedback(tmp_path):
    out = feedback.write_feedback(tmp_path, "demo", ["fix naming", "add a test"])
    assert out.exists()
    text = out.read_text()
    assert "fix naming" in text and "add a test" in text


def test_create_followup_prompt(tmp_path):
    dossier = Dossier(repo="demo", task="Add feature", summary="did it")
    prompt_file, command = feedback.create_followup_prompt(
        tmp_path, "demo", dossier, ["rename foo to bar"]
    )
    assert prompt_file.exists()
    body = prompt_file.read_text()
    assert "rename foo to bar" in body
    assert "demo" in body
    assert command.startswith(f"cd {tmp_path}")
    assert "claude -p" in command


def test_followup_with_no_items_still_writes(tmp_path):
    dossier = Dossier(repo="demo")
    prompt_file, command = feedback.create_followup_prompt(tmp_path, "demo", dossier, [])
    assert prompt_file.exists()
    assert "claude -p" in command


# --- regression: Codex finding #3 (handoff command must be shell-safe) ----------------


def test_followup_command_is_shell_safe_for_paths_with_metacharacters(tmp_path):
    import shlex

    weird = tmp_path / "has space & $danger"
    weird.mkdir()
    dossier = Dossier(repo="demo")
    prompt_file, command = feedback.create_followup_prompt(weird, "demo", dossier, ["do x"])

    # Paths appear in their quoted form...
    assert shlex.quote(str(weird)) in command
    assert shlex.quote(str(prompt_file)) in command
    # ...and never as a raw, unquoted argument that the shell would mis-split.
    assert f"cd {weird} &&" not in command
