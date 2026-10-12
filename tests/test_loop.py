import json
from pathlib import Path
from typing import Any, Dict

from task_board.loop import (
    LoopState,
    VerificationResult,
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
