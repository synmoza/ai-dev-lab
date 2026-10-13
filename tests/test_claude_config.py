import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "authority_guard.py"


def _run_hook(
    tool_name: str,
    tool_input: Dict[str, Any],
    agent_type: Optional[str] = None,
) -> subprocess.CompletedProcess:
    event: Dict[str, Any] = {
        "hook_event_name": "PreToolUse",
        "cwd": str(ROOT),
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    if agent_type is not None:
        event["agent_id"] = "test-agent"
        event["agent_type"] = agent_type
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)},
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "path",
    ["src/task_board/service.py", "tests/test_new.py", "evidence/note.md"],
)
def test_maker_may_write_policy_writable_paths(path: str) -> None:
    result = _run_hook("Edit", {"file_path": str(ROOT / path)})

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "path",
    [
        "specs/task-board.md",
        "tasks/queue.yaml",
        "policies/agent-authority.yaml",
        ".claude/settings.json",
        "scripts/verify.sh",
        "AGENTS.md",
        "src/../specs/task-board.md",
    ],
)
def test_maker_may_not_write_human_owned_paths(path: str) -> None:
    result = _run_hook("Write", {"file_path": str(ROOT / path)})

    assert result.returncode == 2
    assert "authority guard" in result.stderr


def test_maker_may_not_write_outside_the_lab(tmp_path: Path) -> None:
    result = _run_hook("Write", {"file_path": str(tmp_path / "x.py")})

    assert result.returncode == 2
    assert "outside the lab" in result.stderr


def test_checker_may_not_write_anything() -> None:
    result = _run_hook(
        "Edit",
        {"file_path": str(ROOT / "src" / "task_board" / "service.py")},
        agent_type="checker",
    )

    assert result.returncode == 2


@pytest.mark.parametrize(
    "command",
    [
        "scripts/verify.sh full",
        "./scripts/verify.sh fast",
        "git diff main",
        "git status",
    ],
)
def test_checker_may_run_read_only_commands(command: str) -> None:
    result = _run_hook("Bash", {"command": command}, agent_type="checker")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "sed -i s/a/b/ src/task_board/service.py",
        "git diff main > out.diff",
        "git diff --output=out.diff",
        "scripts/verify.sh full; touch x",
        "scripts/verify.sh full extra",
        "git commit -m done",
    ],
)
def test_checker_bash_is_limited(command: str) -> None:
    result = _run_hook("Bash", {"command": command}, agent_type="checker")

    assert result.returncode == 2


def test_maker_bash_is_left_to_permissions_and_sandbox() -> None:
    result = _run_hook("Bash", {"command": "scripts/verify.sh fast"})

    assert result.returncode == 0


def test_malformed_event_fails_closed() -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json",
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2


def test_settings_enforce_sandbox_and_deny_side_effects() -> None:
    settings = json.loads(
        (ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    deny = settings["permissions"]["deny"]

    for rule in (
        "Bash(git push *)",
        "Bash(git merge *)",
        "Bash(scripts/bootstrap.sh *)",
        "Bash(scripts/collect-evidence.sh *)",
        "WebFetch",
    ):
        assert rule in deny
    assert "Bash(git commit *)" in settings["permissions"]["ask"]
    sandbox = settings["sandbox"]
    assert sandbox["enabled"] is True
    assert sandbox["allowUnsandboxedCommands"] is False
    assert sandbox["network"]["allowedDomains"] == []
    for path in ("./specs", "./tasks", "./policies", "./.claude"):
        assert path in sandbox["filesystem"]["denyWrite"]
    hook = settings["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "Edit|Write|MultiEdit|NotebookEdit|Bash"
    assert "authority_guard.py" in hook["hooks"][0]["command"]


def test_checker_agent_has_no_write_tools() -> None:
    agent = (ROOT / ".claude" / "agents" / "checker.md").read_text(encoding="utf-8")
    frontmatter = agent.split("---")[1]

    assert "name: checker" in frontmatter
    assert "tools: Read, Grep, Glob, Bash" in frontmatter
    assert "disallowedTools: Write, Edit, MultiEdit, NotebookEdit" in frontmatter
