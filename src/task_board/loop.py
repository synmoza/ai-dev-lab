"""A bounded, persistent loop for teaching stop and recovery behavior."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

from task_board.domain import DataFormatError

TERMINAL_STATUSES = frozenset({"done", "blocked", "escalated", "aborted"})
SWITCHABLE_STATUSES = frozenset({"ready", "done"})
TASK_ID_PATTERN = re.compile(r"TB-LAB-[0-9]{3}")


@dataclass(frozen=True)
class VerificationResult:
    """The observable result from one verifier invocation."""

    exit_code: int
    output: str


@dataclass(frozen=True)
class LoopState:
    """Durable snapshot used to resume a bounded loop."""

    status: str
    attempt: int
    same_failure_count: int
    last_failure_signature: Optional[str]
    next_sequence: int
    terminal_reason: Optional[str]
    task_id: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "LoopState":
        required = {
            "status",
            "attempt",
            "same_failure_count",
            "last_failure_signature",
            "next_sequence",
            "terminal_reason",
        }
        # Snapshots written before task binding have no task_id: unbound.
        if set(raw) - {"task_id"} != required:
            raise DataFormatError("loop state has unexpected fields")
        state = cls(
            status=_require_string(raw, "status"),
            attempt=_require_nonnegative_int(raw, "attempt"),
            same_failure_count=_require_nonnegative_int(raw, "same_failure_count"),
            last_failure_signature=_optional_string(raw, "last_failure_signature"),
            next_sequence=_require_positive_int(raw, "next_sequence"),
            terminal_reason=_optional_string(raw, "terminal_reason"),
            task_id=_optional_string(raw, "task_id") if "task_id" in raw else None,
        )
        if state.status not in {
            "ready",
            "retrying",
            *TERMINAL_STATUSES,
        }:
            raise DataFormatError("loop state has an unknown status")
        return state

    def to_dict(self) -> Dict[str, Any]:
        return _with_task_id(
            {
                "attempt": self.attempt,
                "last_failure_signature": self.last_failure_signature,
                "next_sequence": self.next_sequence,
                "same_failure_count": self.same_failure_count,
                "status": self.status,
                "terminal_reason": self.terminal_reason,
            },
            self.task_id,
        )


Verifier = Callable[[str], VerificationResult]


def run_loop(
    root: Path,
    verifier: Optional[Verifier] = None,
    max_steps: Optional[int] = None,
    task_id: Optional[str] = None,
) -> int:
    """Run until pass, environment error, escalation, or budget exhaustion.

    With ``max_steps``, pause after that many retryable rounds and return 1 so
    the maker can change the code before the next step. Round budget and
    same-failure limit still apply across steps.

    With ``task_id``, bind the loop to that task. A different task, or no
    snapshot at all, starts again from attempt 0; the same task resumes, so
    its terminal decision still stands. Switching is refused unless the
    current snapshot is ``ready`` or ``done``, so a retrying, escalated,
    blocked, or aborted loop cannot be cleared by naming another task.
    """

    if task_id is not None:
        _validate_task_id(root, task_id)
    contract = _load_contract(root / ".ai-loop" / "loop-contract.yaml")
    state_path = root / ".ai-loop" / "state.yaml"
    state_exists = state_path.exists()
    state = _load_state(state_path)
    if task_id is not None and (not state_exists or state.task_id != task_id):
        if state_exists and state.status not in SWITCHABLE_STATUSES:
            raise DataFormatError(
                f"loop is {state.status} on task {state.task_id or 'unbound'}; "
                f"cannot switch to {task_id} until the human owner resolves it"
            )
        state = _start_task(root, state, task_id)
    if state.status in TERMINAL_STATUSES:
        _write_terminal_status(state)
        return 0 if state.status == "done" else 2

    execute = verifier or (lambda mode: _run_verifier(root, mode))
    steps = 0
    while state.attempt < contract["max_rounds"]:
        if max_steps is not None and steps >= max_steps:
            _write_paused_status(state, contract["max_rounds"])
            return 1
        steps += 1
        result = execute(contract["verification_mode"])
        next_attempt = state.attempt + 1
        signature = _failure_signature(result)
        same_failure_count = _same_failure_count(state, signature)
        evidence_ref = _persist_verifier_result(
            root,
            next_attempt,
            result,
            signature,
            state.task_id,
        )
        status, reason = _decide(
            result=result,
            attempt=next_attempt,
            max_rounds=contract["max_rounds"],
            same_failure_count=same_failure_count,
            same_failure_limit=contract["same_failure_limit"],
        )
        next_state = LoopState(
            status=status,
            attempt=next_attempt,
            same_failure_count=same_failure_count,
            last_failure_signature=signature,
            next_sequence=state.next_sequence + 1,
            terminal_reason=reason if status in TERMINAL_STATUSES else None,
            task_id=state.task_id,
        )
        _write_json_atomic(state_path, next_state.to_dict())
        _append_event(
            root=root,
            sequence=state.next_sequence,
            from_status=state.status,
            to_status=status,
            reason=reason,
            evidence_ref=evidence_ref,
            task_id=state.task_id,
        )
        state = next_state
        if status != "retrying":
            _write_terminal_status(state)
            return 0 if status == "done" else 2
    raise DataFormatError("loop stopped without a terminal decision")


def _validate_task_id(root: Path, task_id: str) -> None:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise DataFormatError("task id must look like TB-LAB-NNN")
    if not (root / "tasks" / f"{task_id}.md").is_file():
        raise DataFormatError(f"task contract not found: tasks/{task_id}.md")


def _start_task(root: Path, old_state: LoopState, task_id: str) -> LoopState:
    """Start a bound task at attempt 0 without deleting prior history."""

    new_state = LoopState(
        status="ready",
        attempt=0,
        same_failure_count=0,
        last_failure_signature=None,
        next_sequence=old_state.next_sequence + 1,
        terminal_reason=None,
        task_id=task_id,
    )
    _write_json_atomic(root / ".ai-loop" / "state.yaml", new_state.to_dict())
    _append_event(
        root=root,
        sequence=old_state.next_sequence,
        from_status=old_state.status,
        to_status="ready",
        reason="new-task-started",
        evidence_ref=None,
        task_id=task_id,
    )
    return new_state


def reset_loop(root: Path) -> int:
    """Start a new attempt without deleting prior events or evidence."""

    state_path = root / ".ai-loop" / "state.yaml"
    old_state = _load_state(state_path)
    new_state = LoopState(
        status="ready",
        attempt=0,
        same_failure_count=0,
        last_failure_signature=None,
        next_sequence=old_state.next_sequence + 1,
        terminal_reason=None,
    )
    _write_json_atomic(state_path, new_state.to_dict())
    _append_event(
        root=root,
        sequence=old_state.next_sequence,
        from_status=old_state.status,
        to_status="ready",
        reason="human-reset-with-evidence-preserved",
        evidence_ref=None,
    )
    sys.stdout.write("loop reset: prior evidence preserved\n")
    return 0


def show_status(root: Path) -> int:
    state = _load_state(root / ".ai-loop" / "state.yaml")
    sys.stdout.write(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="bounded-loop")
    parser.add_argument("--root", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run")
    step = commands.add_parser("step")
    step.add_argument("task_id", nargs="?")
    commands.add_parser("demo-repeated-failure")
    commands.add_parser("reset")
    commands.add_parser("status")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "run":
            return run_loop(root)
        if args.command == "step":
            return run_loop(root, max_steps=1, task_id=args.task_id)
        if args.command == "demo-repeated-failure":
            return run_loop(
                root,
                verifier=lambda mode: _run_demo_verifier(root, "fail"),
            )
        if args.command == "reset":
            return reset_loop(root)
        if args.command == "status":
            return show_status(root)
    except DataFormatError as exc:
        sys.stderr.write(f"bounded-loop environment error: {exc}\n")
        return 2
    sys.stderr.write("bounded-loop environment error: unsupported command\n")
    return 2


def _load_contract(path: Path) -> Dict[str, Any]:
    raw = _load_json_object(path)
    loop = raw.get("loop")
    if not isinstance(loop, dict):
        raise DataFormatError("loop contract must contain a loop object")
    verification = loop.get("verification")
    if not isinstance(verification, dict):
        raise DataFormatError("loop contract needs verification settings")
    return {
        "max_rounds": _positive_int_value(loop.get("max_rounds"), "max_rounds"),
        "same_failure_limit": _positive_int_value(
            loop.get("same_failure_limit"),
            "same_failure_limit",
        ),
        "verification_mode": _mode_value(verification.get("mode")),
    }


def _load_state(path: Path) -> LoopState:
    """Load the local snapshot, or start fresh when none exists yet.

    The snapshot is gitignored so loop runs never dirty the tracked tree.
    A fresh state continues event numbering after any preserved events.
    """

    if not path.exists():
        return LoopState(
            status="ready",
            attempt=0,
            same_failure_count=0,
            last_failure_signature=None,
            next_sequence=_count_events(path.parent / "events.jsonl") + 1,
            terminal_reason=None,
        )
    return LoopState.from_dict(_load_json_object(path))


def _count_events(path: Path) -> int:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise DataFormatError(f"cannot read {path.name}: {exc}") from exc
    return sum(1 for line in lines if line.strip())


def _load_json_object(path: Path) -> Dict[str, Any]:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataFormatError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise DataFormatError(f"{path.name} root must be an object")
    return raw


def _run_verifier(root: Path, mode: str) -> VerificationResult:
    completed = subprocess.run(
        [str(root / "scripts" / "verify.sh"), mode],
        cwd=root,
        env=_python_environment(root),
        check=False,
        capture_output=True,
        text=True,
    )
    return VerificationResult(
        exit_code=completed.returncode,
        output=f"{completed.stdout}{completed.stderr}",
    )


def _run_demo_verifier(root: Path, result: str) -> VerificationResult:
    completed = subprocess.run(
        [sys.executable, "-m", "task_board.demo_verifier", result],
        cwd=root,
        env=_python_environment(root),
        check=False,
        capture_output=True,
        text=True,
    )
    return VerificationResult(
        exit_code=completed.returncode,
        output=f"{completed.stdout}{completed.stderr}",
    )


def _python_environment(root: Path) -> Dict[str, str]:
    environment = os.environ.copy()
    source = str(root / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{source}{os.pathsep}{existing}" if existing else source
    )
    return environment


def _failure_signature(result: VerificationResult) -> Optional[str]:
    if result.exit_code == 0:
        return None
    payload = f"{result.exit_code}\n{result.output}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _same_failure_count(
    state: LoopState,
    signature: Optional[str],
) -> int:
    if signature is None:
        return 0
    if signature == state.last_failure_signature:
        return state.same_failure_count + 1
    return 1


def _decide(
    result: VerificationResult,
    attempt: int,
    max_rounds: int,
    same_failure_count: int,
    same_failure_limit: int,
) -> Tuple[str, str]:
    if result.exit_code == 0:
        return "done", "verifier-passed"
    if result.exit_code == 2:
        return "blocked", "verifier-environment-error"
    if result.exit_code != 1:
        return "blocked", f"unexpected-verifier-exit-{result.exit_code}"
    if same_failure_count >= same_failure_limit:
        return "escalated", "same-failure-limit-reached"
    if attempt >= max_rounds:
        return "blocked", "round-budget-exhausted"
    return "retrying", "acceptance-failure-retryable"


def _persist_verifier_result(
    root: Path,
    attempt: int,
    result: VerificationResult,
    signature: Optional[str],
    task_id: Optional[str] = None,
) -> str:
    timestamp = _utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    relative = Path("evidence") / "loop-runs" / (f"attempt-{attempt:03d}-{timestamp}")
    run_dir = root / relative
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "verifier.out").write_text(result.output, encoding="utf-8")
    _write_json_atomic(
        run_dir / "result.json",
        _with_task_id(
            {
                "attempt": attempt,
                "exit_code": result.exit_code,
                "failure_signature": signature,
                "recorded_at": _utc_now().isoformat(),
            },
            task_id,
        ),
    )
    return str(relative)


def _append_event(
    root: Path,
    sequence: int,
    from_status: str,
    to_status: str,
    reason: str,
    evidence_ref: Optional[str],
    task_id: Optional[str] = None,
) -> None:
    event = {
        "actor": "bounded-loop-driver",
        "evidence_ref": evidence_ref,
        "from": from_status,
        "id": f"event-{sequence:04d}",
        "reason": reason,
        "sequence": sequence,
        "time": _utc_now().isoformat(),
        "to": to_status,
    }
    event = _with_task_id(event, task_id)
    path = root / ".ai-loop" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _with_task_id(payload: Dict[str, Any], task_id: Optional[str]) -> Dict[str, Any]:
    """Record the bound task; unbound records keep their original shape."""

    if task_id is not None:
        payload["task_id"] = task_id
    return payload


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        raise DataFormatError(f"cannot write {path.name}: {exc}") from exc
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_terminal_status(state: LoopState) -> None:
    stream = sys.stdout if state.status == "done" else sys.stderr
    stream.write(
        f"loop terminal: {state.status}; "
        f"reason={state.terminal_reason}; attempts={state.attempt}\n"
    )


def _write_paused_status(state: LoopState, max_rounds: int) -> None:
    sys.stderr.write(
        f"loop paused: {state.status}; attempts={state.attempt}/{max_rounds}; "
        "change the code, then run step again\n"
    )


def _require_string(raw: Dict[str, Any], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value:
        raise DataFormatError(f"{key} must be a non-empty string")
    return value


def _optional_string(raw: Dict[str, Any], key: str) -> Optional[str]:
    value = raw[key]
    if value is None or isinstance(value, str):
        return value
    raise DataFormatError(f"{key} must be a string or null")


def _require_nonnegative_int(raw: Dict[str, Any], key: str) -> int:
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DataFormatError(f"{key} must be a nonnegative integer")
    return value


def _require_positive_int(raw: Dict[str, Any], key: str) -> int:
    value = _require_nonnegative_int(raw, key)
    if value == 0:
        raise DataFormatError(f"{key} must be positive")
    return value


def _positive_int_value(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DataFormatError(f"{name} must be a positive integer")
    return value


def _mode_value(value: Any) -> str:
    if value not in {"fast", "full"}:
        raise DataFormatError("verification mode must be fast or full")
    return str(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
