import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from graderguard.sandbox import (
    OUTPUT_TAIL_CHARS,
    base_env,
    diff_snapshots,
    install_tests,
    remove_path,
    run_command,
    sandbox_for,
    snapshot,
)
from graderguard.task import load_task

TaskFactory = Callable[..., Path]


def test_run_command_captures_exit_code_and_output(tmp_path: Path) -> None:
    result = run_command(
        "echo hello; echo oops >&2; exit 3", cwd=tmp_path, env=base_env(tmp_path), timeout=10
    )
    assert result.exit_code == 3
    assert not result.succeeded
    assert "hello" in result.output
    assert "oops" in result.output
    assert result.timed_out is False


def test_run_command_success_and_memory_limit_argument(tmp_path: Path) -> None:
    result = run_command(
        "python -c 'print(1 + 1)'", cwd=tmp_path, env=base_env(tmp_path), timeout=30, memory_mb=512
    )
    assert result.succeeded
    assert result.output.strip() == "2"


def test_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "late.txt"
    start = time.monotonic()
    result = run_command(
        f"(sleep 3; touch {marker}) & sleep 30",
        cwd=tmp_path,
        env=base_env(tmp_path),
        timeout=0.5,
    )
    assert result.timed_out
    assert result.exit_code is None
    assert not result.succeeded
    assert time.monotonic() - start < 10
    time.sleep(3.5)
    assert not marker.exists(), "background child survived the timeout"


def test_output_is_truncated_to_the_tail(tmp_path: Path) -> None:
    result = run_command(
        "python -c \"print('x' * 10000 + 'END')\"",
        cwd=tmp_path,
        env=base_env(tmp_path),
        timeout=30,
    )
    assert len(result.output) == OUTPUT_TAIL_CHARS
    assert result.output.rstrip().endswith("END")


def test_environment_is_scrubbed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GG_SECRET_TOKEN", "leak")
    result = run_command("env", cwd=tmp_path, env=base_env(tmp_path), timeout=10)
    assert "GG_SECRET_TOKEN" not in result.output
    assert "PYTHONHASHSEED=0" in result.output
    assert "TZ=UTC" in result.output


def test_sandbox_hides_tests_until_install(make_task: TaskFactory) -> None:
    task = load_task(make_task())
    with sandbox_for(task) as box:
        assert (box.workspace / "README.txt").is_file()
        assert not (box.workspace / "tests").exists()
        assert box.env["HOME"] == str(box.home)
        install_tests(task, box.workspace)
        assert (box.workspace / "tests" / "test_answer.py").is_file()
        root = box.root
    assert not root.exists()


def test_visible_tests_are_refreshed_before_grading(make_task: TaskFactory) -> None:
    task = load_task(make_task(agent="tests_visible = true"))
    with sandbox_for(task) as box:
        test_file = box.workspace / "tests" / "test_answer.py"
        test_file.write_text("def test_nothing():\n    pass\n")
        (box.workspace / "tests" / "extra.py").write_text("")
        install_tests(task, box.workspace)
        assert "42" in test_file.read_text()
        assert not (box.workspace / "tests" / "extra.py").exists()


def test_visible_tests_without_refresh_keep_agent_edits(make_task: TaskFactory) -> None:
    task = load_task(make_task(agent="tests_visible = true", grader_extra="refresh_tests = false"))
    with sandbox_for(task, keep=True) as box:
        test_file = box.workspace / "tests" / "test_answer.py"
        test_file.write_text("edited\n")
        install_tests(task, box.workspace)
        assert test_file.read_text() == "edited\n"
    assert box.root.exists()
    remove_path(box.root)
    assert not box.root.exists()


def test_sandbox_without_environment_starts_empty(make_task: TaskFactory) -> None:
    root = make_task()
    remove_path(root / "environment")
    with sandbox_for(load_task(root)) as box:
        assert list(box.workspace.iterdir()) == []


def test_snapshot_diff_reports_added_modified_deleted(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("same")
    (tmp_path / "edit.txt").write_text("before")
    (tmp_path / "gone.txt").write_text("bye")
    (tmp_path / "sub").mkdir()
    before = snapshot(tmp_path)
    (tmp_path / "edit.txt").write_text("after")
    (tmp_path / "gone.txt").unlink()
    (tmp_path / "sub" / "new.txt").write_text("hi")
    os.symlink("keep.txt", tmp_path / "link.txt")
    os.symlink("sub", tmp_path / "dirlink")
    after = snapshot(tmp_path)
    assert after["link.txt"] == "link:keep.txt"
    assert after["dirlink"] == "link:sub"
    changes = [(c.kind, c.path) for c in diff_snapshots(before, after)]
    assert changes == [
        ("A", "dirlink"),
        ("M", "edit.txt"),
        ("D", "gone.txt"),
        ("A", "link.txt"),
        ("A", "sub/new.txt"),
    ]


def test_remove_path_handles_files_links_dirs_and_missing(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x")
    (tmp_path / "d").mkdir()
    os.symlink("d", tmp_path / "l")
    for name in ("l", "f", "d", "missing"):
        remove_path(tmp_path / name)
    assert list(tmp_path.iterdir()) == []
