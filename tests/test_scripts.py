import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]


def _environment() -> Dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return environment


def _copy_tracked_files(source: Path, destination: Path) -> None:
    """Copy only the files `git ls-files` lists; never read untracked files."""
    listed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=source,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    destination.mkdir(parents=True)
    for relative in filter(None, listed.split("\0")):
        source_file = source / relative
        if not source_file.is_symlink() and not source_file.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target, follow_symlinks=False)


def test_copy_tracked_files_skips_unreadable_untracked_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    tracked = source / "nested" / "tracked.txt"
    tracked.write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "nested/tracked.txt"], cwd=source, check=True)
    untracked = source / ".untracked-placeholder"
    untracked.write_text("secret\n", encoding="utf-8")
    untracked.chmod(0o000)
    destination = tmp_path / "copy"

    try:
        _copy_tracked_files(source, destination)
    finally:
        untracked.chmod(0o600)

    copied = sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    )
    assert copied == ["nested/tracked.txt"]
    assert (destination / "nested" / "tracked.txt").read_text(
        encoding="utf-8"
    ) == "tracked\n"


def test_guard_rejects_unlisted_action() -> None:
    completed = subprocess.run(
        ["bash", "scripts/guard-command.sh", "delete-everything"],
        cwd=ROOT,
        env=_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "guard rejected" in completed.stderr


def test_guard_runs_task_board_without_shell_interpolation(
    tmp_path: Path,
) -> None:
    store = tmp_path / "tasks.json"
    title = "Keep $(commands) as plain text"
    completed = subprocess.run(
        [
            "bash",
            "scripts/guard-command.sh",
            "task-board",
            "--store",
            str(store),
            "add",
            title,
        ],
        cwd=ROOT,
        env=_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert title in completed.stdout
    assert not (ROOT / "commands").exists()


def test_control_scripts_classify_failures_deterministically(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        ["python3", "-m", "task_board.demo_verifier", "fail"],
        cwd=ROOT,
        env=_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == ("PEDAGOGICAL_DEMO: repeated acceptance failure\n")

    isolated_python = tmp_path / "python-without-site-packages"
    isolated_python.write_text(
        "#!/usr/bin/env bash\n" f'exec {shlex.quote(sys.executable)} -S "$@"\n',
        encoding="utf-8",
    )
    isolated_python.chmod(0o755)
    environment = _environment()
    environment["PYTHON_BIN"] = str(isolated_python)

    missing_pytest = subprocess.run(
        ["bash", "scripts/verify.sh", "fast"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert missing_pytest.returncode == 2
    assert "environment error" in missing_pytest.stderr
    assert "missing pytest" in missing_pytest.stderr

    verify_script = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    assert '"$python_bin" -m compileall -q -f src tests' in verify_script
    assert 'PYTHONPYCACHEPREFIX="$root/runtime/pycache"' in verify_script

    pycache_root = tmp_path / "contained-pycache"
    cache_probe = _environment()
    cache_probe["PYTHONPYCACHEPREFIX"] = str(pycache_root)
    cache_path = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.util; "
            "print(importlib.util.cache_from_source('src/task_board/service.py'))",
        ],
        cwd=ROOT,
        env=cache_probe,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert Path(cache_path).is_relative_to(pycache_root)


def test_evidence_collector_rejects_tracked_dirty_source(tmp_path: Path) -> None:
    lab_copy = tmp_path / "ai-dev-lab"
    _copy_tracked_files(ROOT, lab_copy)
    subprocess.run(["git", "init", "-q"], cwd=lab_copy, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Evidence Test"],
        cwd=lab_copy,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "evidence-test@localhost"],
        cwd=lab_copy,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=lab_copy, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "test: establish collector baseline"],
        cwd=lab_copy,
        check=True,
    )
    source_files, copy_files = (
        subprocess.run(
            ["git", "ls-files"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for repo in (ROOT, lab_copy)
    )
    assert copy_files == source_files
    readme = lab_copy / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\ntracked dirty probe\n",
        encoding="utf-8",
    )
    environment = _environment()
    environment["PYTHON_BIN"] = sys.executable
    environment["RUN_ID"] = "tracked-dirty-probe"

    completed = subprocess.run(
        ["bash", "scripts/collect-evidence.sh", "fast"],
        cwd=lab_copy,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    run = lab_copy / "evidence" / "runs" / "tracked-dirty-probe"
    assert completed.returncode == 2
    assert (run / "status.txt").read_text(encoding="utf-8").strip()
    assert (run / "change.diff").read_text(encoding="utf-8").strip()
    assert "verification not run" in (run / "verifier.out").read_text(encoding="utf-8")


def test_guard_delete_treats_shell_syntax_as_plain_id(tmp_path: Path) -> None:
    store = tmp_path / "tasks.json"
    task_id = "$(touch pwned)"
    completed = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts" / "guard-command.sh"),
            "task-board",
            "--store",
            str(store),
            "delete",
            task_id,
        ],
        cwd=tmp_path,
        env=_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert f"task not found: {task_id}" in completed.stderr
    assert not (tmp_path / "pwned").exists()
    assert not (ROOT / "pwned").exists()
