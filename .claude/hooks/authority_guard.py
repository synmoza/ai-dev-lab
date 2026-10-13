"""PreToolUse hook that enforces policies/agent-authority.yaml for Claude Code.

The main conversation acts as the maker; the `checker` subagent acts as the
checker. File tools may only write inside the role's writable paths. The
checker may only run the read-only commands it is allowed in Bash.

Exit 0 lets Claude Code's normal permission flow decide. Exit 2 blocks the
tool call and shows stderr to Claude. Anything the hook cannot evaluate is
blocked, so a broken policy fails closed.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

FILE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
CHECKER_AGENT = "checker"
CHECKER_COMMANDS = (
    ("scripts/verify.sh", "fast"),
    ("scripts/verify.sh", "full"),
    ("git", "diff"),
    ("git", "status"),
    ("git", "log"),
    ("git", "show"),
)
SHELL_CONTROL = re.compile(r"[;&|<>`$(){}\n]")


def main(stdin: Optional[str] = None) -> int:
    try:
        event: Dict[str, Any] = json.loads(sys.stdin.read() if stdin is None else stdin)
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event["cwd"]).resolve()
        role = "checker" if event.get("agent_type") == CHECKER_AGENT else "maker"
        policy = _load_role(root, role)
        tool = event["tool_name"]
        tool_input = event.get("tool_input") or {}
        if tool in FILE_TOOLS:
            return _check_file_write(root, role, policy, tool_input)
        if tool == "Bash" and role == "checker":
            return _check_checker_command(tool_input.get("command", ""))
        return 0
    except Exception as exc:  # fail closed on any malformed input or policy
        return _deny(f"authority guard could not evaluate the call: {exc}")


def _load_role(root: Path, role: str) -> Dict[str, Any]:
    raw = json.loads(
        (root / "policies" / "agent-authority.yaml").read_text(encoding="utf-8")
    )
    return raw["roles"][role]


def _check_file_write(
    root: Path, role: str, policy: Dict[str, Any], tool_input: Dict[str, Any]
) -> int:
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw_path:
        return _deny("file tool call has no path")
    target = Path(raw_path)
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    try:
        relative = target.relative_to(root).as_posix()
    except ValueError:
        return _deny(f"{role} may not write outside the lab: {raw_path}")
    writable: Sequence[str] = policy.get("writable_paths", [])
    if _matches(relative, writable):
        return 0
    allowed = ", ".join(writable) or "nothing"
    return _deny(
        f"{role} may not write {relative}; writable paths are: {allowed}. "
        "Spec, task, policy, and config changes belong to the human owner."
    )


def _matches(relative: str, allowed: Sequence[str]) -> bool:
    return any(
        relative == path.rstrip("/")
        or (path.endswith("/") and relative.startswith(path))
        for path in allowed
    )


def _check_checker_command(command: str) -> int:
    if SHELL_CONTROL.search(command):
        return _deny("checker commands may not use shell operators or substitution")
    words = shlex.split(command)
    if any(word.startswith(("--output", "--ext-diff")) for word in words):
        return _deny("checker git commands may not write files or run diff tools")
    if words[:1] == ["./scripts/verify.sh"]:
        words[0] = "scripts/verify.sh"
    for program, first_arg in CHECKER_COMMANDS:
        if words[:2] == [program, first_arg]:
            if program == "scripts/verify.sh" and len(words) != 2:
                break
            return 0
    allowed = ", ".join(" ".join(pair) for pair in CHECKER_COMMANDS)
    return _deny(f"checker may only run: {allowed}")


def _deny(reason: str) -> int:
    sys.stderr.write(f"authority guard: {reason}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
