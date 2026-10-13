import json
from pathlib import Path

import pytest

from task_board.domain import DataFormatError, TaskNotFoundError, ValidationError
from task_board.repository import TaskRepository
from task_board.service import TaskService


def _service(path: Path) -> TaskService:
    return TaskService(TaskRepository(path))


def test_add_list_and_complete_round_trip(tmp_path: Path) -> None:
    store = tmp_path / "tasks.json"
    service = _service(store)

    first = service.add("  Verify the baseline  ", "high")
    second = service.add("Record evidence", "medium")
    completed = service.complete(first.task_id)

    assert first.task_id == "TB-001"
    assert first.title == "Verify the baseline"
    assert second.task_id == "TB-002"
    assert completed.status == "done"
    assert [task.task_id for task in service.list("todo")] == ["TB-002"]
    assert service.show("TB-001").status == "done"


def test_blank_title_does_not_create_store(tmp_path: Path) -> None:
    store = tmp_path / "tasks.json"

    with pytest.raises(ValidationError, match="must not be blank"):
        _service(store).add(" ", "low")

    assert not store.exists()


def test_missing_task_is_reported(tmp_path: Path) -> None:
    with pytest.raises(TaskNotFoundError, match="TB-999"):
        _service(tmp_path / "tasks.json").complete("TB-999")


def test_corrupt_store_is_not_overwritten(tmp_path: Path) -> None:
    store = tmp_path / "tasks.json"
    store.write_text('{"not": "a list"}', encoding="utf-8")

    with pytest.raises(DataFormatError, match="JSON array"):
        _service(store).add("Safe change", "low")

    assert json.loads(store.read_text(encoding="utf-8")) == {"not": "a list"}


def test_list_sorts_valid_records_loaded_out_of_order(tmp_path: Path) -> None:
    store = tmp_path / "tasks.json"
    store.write_text(
        json.dumps(
            [
                {
                    "id": "TB-002",
                    "title": "Second",
                    "priority": "medium",
                    "status": "todo",
                },
                {
                    "id": "TB-001",
                    "title": "First",
                    "priority": "high",
                    "status": "done",
                },
            ]
        ),
        encoding="utf-8",
    )

    assert [task.task_id for task in _service(store).list()] == [
        "TB-001",
        "TB-002",
    ]


def test_delete_removes_only_the_requested_task(tmp_path: Path) -> None:
    service = _service(tmp_path / "tasks.json")
    first = service.add("First", "high")
    second = service.add("Second", "low")
    third = service.add("Third", "medium")

    deleted = service.delete(second.task_id)

    assert deleted == second
    assert service.list() == (first, third)


def test_delete_accepts_todo_and_done_tasks(tmp_path: Path) -> None:
    service = _service(tmp_path / "tasks.json")
    todo = service.add("Still open", "low")
    done = service.complete(service.add("Finished", "high").task_id)

    assert service.delete(done.task_id).status == "done"
    assert service.delete(todo.task_id).status == "todo"
    assert service.list() == ()


def test_delete_unknown_task_keeps_store_bytes(tmp_path: Path) -> None:
    store = tmp_path / "tasks.json"
    service = _service(store)
    service.add("Keep me", "medium")
    before = store.read_bytes()

    with pytest.raises(TaskNotFoundError, match="task not found: TB-999"):
        service.delete("TB-999")

    assert store.read_bytes() == before


def test_delete_without_store_does_not_create_it(tmp_path: Path) -> None:
    store = tmp_path / "tasks.json"

    with pytest.raises(TaskNotFoundError, match="TB-001"):
        _service(store).delete("TB-001")

    assert not store.exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [("{broken", "cannot read task store"), ('{"not": "a list"}', "JSON array")],
)
def test_delete_rejects_corrupt_store_without_overwrite(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    store = tmp_path / "tasks.json"
    store.write_text(content, encoding="utf-8")

    with pytest.raises(DataFormatError, match=message):
        _service(store).delete("TB-001")

    assert store.read_text(encoding="utf-8") == content


def test_add_after_delete_uses_remaining_max_plus_one(tmp_path: Path) -> None:
    service = _service(tmp_path / "tasks.json")
    for title in ("First", "Second", "Third"):
        service.add(title, "medium")

    service.delete("TB-002")

    assert service.add("Fourth", "low").task_id == "TB-004"
    assert [task.task_id for task in service.list()] == [
        "TB-001",
        "TB-003",
        "TB-004",
    ]
