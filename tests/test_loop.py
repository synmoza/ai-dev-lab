import json
from pathlib import Path
from typing import Any, Dict, Optional

from task_board import loop
from task_board.loop import (
    LoopState,
    VerificationResult,
    main,
    reset_loop,
    run_loop,
)


def _write_loop_files(root: Path) -> None:
    loop_dir = root / ".ai-loop"
    loop_dir.mkdir()
    (loop_dir / "loop-contract.yaml").write_text(
        json.dumps(
            {
                "loop": {
                    "max_rounds": 3,
                    "same_failure_limit": 2,
                    "verification": {"mode": "fast"},
                }
            }
        ),
        encoding="utf-8",
    )
    (loop_dir / "state.yaml").write_text(
        json.dumps(
            LoopState(
                status="ready",
                attempt=0,
                same_failure_count=0,
                last_failure_signature=None,
                next_sequence=1,
                terminal_reason=None,
            ).to_dict()
        ),
        encoding="utf-8",
    )
    (loop_dir / "events.jsonl").write_text("", encoding="utf-8")


def _state(root: Path) -> Dict[str, Any]:
    return json.loads((root / ".ai-loop" / "state.yaml").read_text(encoding="utf-8"))


def test_passing_verifier_stops_after_one_round(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)

    code = run_loop(
        tmp_path,
        verifier=lambda mode: VerificationResult(0, f"{mode}: pass\n"),
    )

    assert code == 0
    assert _state(tmp_path)["status"] == "done"
    assert _state(tmp_path)["attempt"] == 1
    assert len(list((tmp_path / "evidence" / "loop-runs").iterdir())) == 1


def test_same_failure_twice_escalates(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)

    code = run_loop(
        tmp_path,
        verifier=lambda mode: VerificationResult(1, "same failure\n"),
    )

    assert code == 2
    assert _state(tmp_path)["status"] == "escalated"
    assert _state(tmp_path)["attempt"] == 2
    events = (
        (tmp_path / ".ai-loop" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert [json.loads(event)["to"] for event in events] == [
        "retrying",
        "escalated",
    ]


def test_environment_error_blocks_without_retry(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)

    code = run_loop(
        tmp_path,
        verifier=lambda mode: VerificationResult(2, "missing dependency\n"),
    )

    assert code == 2
    assert _state(tmp_path)["status"] == "blocked"
    assert _state(tmp_path)["attempt"] == 1


def test_step_pauses_after_one_retryable_round(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)

    code = run_loop(
        tmp_path,
        verifier=lambda mode: VerificationResult(1, "first failure\n"),
        max_steps=1,
    )

    assert code == 1
    assert _state(tmp_path)["status"] == "retrying"
    assert _state(tmp_path)["attempt"] == 1


def test_steps_with_new_evidence_resume_until_pass(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    outputs = iter(
        [
            VerificationResult(1, "first failure\n"),
            VerificationResult(1, "different failure after a fix\n"),
            VerificationResult(0, "pass\n"),
        ]
    )

    codes = [
        run_loop(tmp_path, verifier=lambda mode: next(outputs), max_steps=1)
        for _ in range(3)
    ]

    assert codes == [1, 1, 0]
    assert _state(tmp_path)["status"] == "done"
    assert _state(tmp_path)["attempt"] == 3


def test_steps_with_same_failure_escalate(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)

    codes = [
        run_loop(
            tmp_path,
            verifier=lambda mode: VerificationResult(1, "same failure\n"),
            max_steps=1,
        )
        for _ in range(2)
    ]

    assert codes == [1, 2]
    assert _state(tmp_path)["status"] == "escalated"


def test_missing_state_starts_fresh_after_preserved_events(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    (tmp_path / ".ai-loop" / "state.yaml").unlink()
    (tmp_path / ".ai-loop" / "events.jsonl").write_text(
        '{"sequence": 1}\n{"sequence": 2}\n',
        encoding="utf-8",
    )

    code = run_loop(
        tmp_path,
        verifier=lambda mode: VerificationResult(0, "pass\n"),
    )

    assert code == 0
    assert _state(tmp_path)["status"] == "done"
    assert _state(tmp_path)["next_sequence"] == 4
    events = (
        (tmp_path / ".ai-loop" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert json.loads(events[-1])["sequence"] == 3


def test_reset_preserves_events_and_evidence(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    run_loop(
        tmp_path,
        verifier=lambda mode: VerificationResult(0, "pass\n"),
    )
    evidence_before = tuple((tmp_path / "evidence" / "loop-runs").iterdir())

    assert reset_loop(tmp_path) == 0

    assert _state(tmp_path)["status"] == "ready"
    assert tuple((tmp_path / "evidence" / "loop-runs").iterdir()) == evidence_before
    events = (
        (tmp_path / ".ai-loop" / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(events) == 2
    assert json.loads(events[-1])["reason"] == ("human-reset-with-evidence-preserved")


TASK = "TB-LAB-901"
OTHER_TASK = "TB-LAB-902"


def _write_task(root: Path, task_id: str) -> None:
    tasks = root / "tasks"
    tasks.mkdir(exist_ok=True)
    (tasks / f"{task_id}.md").write_text(f"# Task {task_id}\n", encoding="utf-8")


def _events(root: Path) -> list:
    path = root / ".ai-loop" / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _evidence_dirs(root: Path) -> list:
    runs = root / "evidence" / "loop-runs"
    return sorted(runs.iterdir()) if runs.exists() else []


def _write_bound_state(root: Path, status: str, task_id: Optional[str]) -> None:
    raw = LoopState(
        status=status,
        attempt=2,
        same_failure_count=2 if status == "escalated" else 0,
        last_failure_signature="abc" if status != "done" else None,
        next_sequence=3,
        terminal_reason=None if status == "ready" else "earlier-decision",
        task_id=task_id,
    ).to_dict()
    (root / ".ai-loop" / "state.yaml").write_text(json.dumps(raw), encoding="utf-8")
    (root / ".ai-loop" / "events.jsonl").write_text(
        '{"sequence": 1}\n{"sequence": 2}\n',
        encoding="utf-8",
    )


def test_step_with_new_task_restarts_and_preserves_history(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)
    run_loop(tmp_path, verifier=lambda mode: VerificationResult(0, "pass\n"))
    evidence_before = _evidence_dirs(tmp_path)

    code = run_loop(
        tmp_path,
        verifier=lambda mode: VerificationResult(1, "first failure\n"),
        max_steps=1,
        task_id=TASK,
    )

    assert code == 1
    state = _state(tmp_path)
    assert state["status"] == "retrying"
    assert state["attempt"] == 1
    assert state["task_id"] == TASK
    events = _events(tmp_path)
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert events[1]["reason"] == "new-task-started"
    assert (events[1]["from"], events[1]["to"]) == ("done", "ready")
    assert events[2]["from"] == "ready"
    evidence_after = _evidence_dirs(tmp_path)
    assert evidence_after[: len(evidence_before)] == evidence_before
    assert len(evidence_after) == len(evidence_before) + 1


def test_step_with_different_task_is_refused_while_unfinished(
    tmp_path: Path,
    capsys: Any,
) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)
    _write_task(tmp_path, OTHER_TASK)
    state_path = tmp_path / ".ai-loop" / "state.yaml"
    events_path = tmp_path / ".ai-loop" / "events.jsonl"

    def verifier(mode: str) -> VerificationResult:
        raise AssertionError("verifier must not run")

    for status in ("retrying", "escalated", "blocked", "aborted"):
        for bound_task in (OTHER_TASK, None):
            _write_bound_state(tmp_path, status, bound_task)
            state_before = state_path.read_bytes()
            events_before = events_path.read_bytes()

            assert main(["--root", str(tmp_path), "step", TASK]) == 2

            message = capsys.readouterr().err
            assert status in message
            assert (bound_task or "unbound") in message
            assert state_path.read_bytes() == state_before
            assert events_path.read_bytes() == events_before
            assert _evidence_dirs(tmp_path) == []


def test_escalation_cannot_be_cleared_by_switching_tasks(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)
    _write_task(tmp_path, OTHER_TASK)
    _write_bound_state(tmp_path, "escalated", TASK)

    def verifier(mode: str) -> VerificationResult:
        raise AssertionError("verifier must not run")

    assert main(["--root", str(tmp_path), "step", OTHER_TASK]) == 2
    code = run_loop(tmp_path, verifier=verifier, max_steps=1, task_id=TASK)
    assert code == 2

    state = _state(tmp_path)
    assert (state["status"], state["task_id"]) == ("escalated", TASK)
    assert len(_events(tmp_path)) == 2


def test_step_with_different_task_starts_from_ready(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)
    _write_bound_state(tmp_path, "ready", OTHER_TASK)

    code = run_loop(
        tmp_path,
        verifier=lambda mode: VerificationResult(0, "pass\n"),
        max_steps=1,
        task_id=TASK,
    )

    assert code == 0
    state = _state(tmp_path)
    assert (state["status"], state["attempt"], state["task_id"]) == ("done", 1, TASK)
    events = _events(tmp_path)
    assert [event["sequence"] for event in events] == [1, 2, 3, 4]
    assert events[2]["reason"] == "new-task-started"
    assert events[2]["from"] == "ready"


def test_step_with_task_and_missing_state_restarts(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)
    (tmp_path / ".ai-loop" / "state.yaml").unlink()
    (tmp_path / ".ai-loop" / "events.jsonl").write_text(
        '{"sequence": 1}\n',
        encoding="utf-8",
    )

    code = run_loop(
        tmp_path,
        verifier=lambda mode: VerificationResult(0, "pass\n"),
        max_steps=1,
        task_id=TASK,
    )

    assert code == 0
    assert _state(tmp_path)["task_id"] == TASK
    events = _events(tmp_path)
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert events[1]["reason"] == "new-task-started"
    assert events[2]["reason"] == "verifier-passed"


def test_step_with_same_done_task_does_not_run_again(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)
    _write_bound_state(tmp_path, "done", TASK)
    state_before = (tmp_path / ".ai-loop" / "state.yaml").read_bytes()
    events_before = (tmp_path / ".ai-loop" / "events.jsonl").read_bytes()

    def verifier(mode: str) -> VerificationResult:
        raise AssertionError("verifier must not run")

    code = run_loop(tmp_path, verifier=verifier, max_steps=1, task_id=TASK)

    assert code == 0
    assert (tmp_path / ".ai-loop" / "state.yaml").read_bytes() == state_before
    assert (tmp_path / ".ai-loop" / "events.jsonl").read_bytes() == events_before
    assert _evidence_dirs(tmp_path) == []


def test_step_with_same_stopped_task_stays_stopped(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)

    def verifier(mode: str) -> VerificationResult:
        raise AssertionError("verifier must not run")

    for status in ("escalated", "blocked"):
        _write_bound_state(tmp_path, status, TASK)
        state_before = (tmp_path / ".ai-loop" / "state.yaml").read_bytes()

        code = run_loop(tmp_path, verifier=verifier, max_steps=1, task_id=TASK)

        assert code == 2
        assert (tmp_path / ".ai-loop" / "state.yaml").read_bytes() == state_before
        assert len(_events(tmp_path)) == 2
        assert _evidence_dirs(tmp_path) == []


def test_task_id_is_recorded_in_state_events_and_result(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)
    outputs = iter(
        [
            VerificationResult(1, "first failure\n"),
            VerificationResult(0, "pass\n"),
        ]
    )

    codes = [
        run_loop(
            tmp_path,
            verifier=lambda mode: next(outputs),
            max_steps=1,
            task_id=TASK,
        )
        for _ in range(2)
    ]

    assert codes == [1, 0]
    assert _state(tmp_path)["task_id"] == TASK
    assert [event["task_id"] for event in _events(tmp_path)] == [TASK] * 3
    results = [
        json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        for run_dir in _evidence_dirs(tmp_path)
    ]
    assert [result["task_id"] for result in results] == [TASK, TASK]
    assert all(
        run_dir.name.startswith("attempt-") and TASK not in run_dir.name
        for run_dir in _evidence_dirs(tmp_path)
    )


def test_legacy_state_without_task_id_is_unbound(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    raw = _state(tmp_path)
    assert "task_id" not in raw

    assert LoopState.from_dict(raw).task_id is None
    assert main(["--root", str(tmp_path), "status"]) == 0


def test_step_without_task_id_keeps_unbound_format(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _write_loop_files(tmp_path)
    monkeypatch.setattr(
        loop,
        "_run_verifier",
        lambda root, mode: VerificationResult(0, "pass\n"),
    )

    assert main(["--root", str(tmp_path), "step"]) == 0

    assert "task_id" not in _state(tmp_path)
    assert all("task_id" not in event for event in _events(tmp_path))
    result = json.loads(
        (_evidence_dirs(tmp_path)[0] / "result.json").read_text(encoding="utf-8")
    )
    assert "task_id" not in result


def test_cli_step_with_task_id_binds_task(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)
    monkeypatch.setattr(
        loop,
        "_run_verifier",
        lambda root, mode: VerificationResult(0, "pass\n"),
    )

    assert main(["--root", str(tmp_path), "step", TASK]) == 0

    assert _state(tmp_path)["task_id"] == TASK
    assert [event["reason"] for event in _events(tmp_path)] == [
        "new-task-started",
        "verifier-passed",
    ]


def test_cli_step_rejects_invalid_or_unknown_task_id(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    _write_task(tmp_path, TASK)
    (tmp_path / "tasks" / "TB-LAB-1.md").write_text("x\n", encoding="utf-8")
    state_path = tmp_path / ".ai-loop" / "state.yaml"
    events_path = tmp_path / ".ai-loop" / "events.jsonl"
    state_before = state_path.read_bytes()
    events_before = events_path.read_bytes()

    for task_id in ("TB-LAB-1", "tb-lab-901", "TB-LAB-9011", "TB-LAB-903", "../x"):
        assert main(["--root", str(tmp_path), "step", task_id]) == 2

        assert state_path.read_bytes() == state_before
        assert events_path.read_bytes() == events_before
        assert _evidence_dirs(tmp_path) == []


def test_cli_step_rejects_task_id_when_state_is_missing(tmp_path: Path) -> None:
    _write_loop_files(tmp_path)
    state_path = tmp_path / ".ai-loop" / "state.yaml"
    state_path.unlink()

    assert main(["--root", str(tmp_path), "step", "TB-LAB-903"]) == 2

    assert not state_path.exists()
    assert (tmp_path / ".ai-loop" / "events.jsonl").read_text(encoding="utf-8") == ""
