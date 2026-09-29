from collections.abc import Callable
from pathlib import Path

import pytest

from graderguard.task import DEFAULT_MEMORY_MB, TaskError, load_task

TaskFactory = Callable[..., Path]


def test_loads_fixture_task_with_defaults(make_task: TaskFactory) -> None:
    task = load_task(make_task())
    assert task.name == "fixture-task"
    assert task.programs == ("main.py",)
    assert task.outputs == ("out/answer.txt",)
    assert task.tests_visible is False
    assert task.refresh_tests is True
    assert task.grader_timeout == 30.0
    assert task.memory_mb == DEFAULT_MEMORY_MB
    assert task.uses_pytest
    assert task.instruction.startswith("Write main.py")
    assert task.environment_dir.name == "environment"


def test_accepts_string_path_and_optional_fields(make_task: TaskFactory) -> None:
    root = make_task(
        toml_extra='description = "d"\n[limits]\nmemory_mb = 512',
        agent="tests_visible = true",
        grader_extra="refresh_tests = false",
    )
    task = load_task(str(root))
    assert task.description == "d"
    assert task.memory_mb == 512
    assert task.programs == ()
    assert task.tests_visible is True
    assert task.refresh_tests is False


def test_missing_directory_and_task_file(tmp_path: Path) -> None:
    with pytest.raises(TaskError, match="not a directory"):
        load_task(tmp_path / "nope")
    with pytest.raises(TaskError, match=r"missing task\.toml"):
        load_task(tmp_path)


def test_invalid_toml(make_task: TaskFactory) -> None:
    root = make_task()
    (root / "task.toml").write_text("name = [\n")
    with pytest.raises(TaskError, match="invalid TOML"):
        load_task(root)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"toml_extra": "colour = 1"}, "unknown key"),
        ({"agent": "program = []"}, r"unknown key\(s\) in \[agent\]"),
        ({"grader_command": " "}, "non-empty string 'command'"),
        ({"agent": "tests_visible = 1"}, "true or false"),
        ({"agent": "programs = 'main.py'"}, "list of strings"),
        ({"agent": "programs = ['../escape.py']"}, "relative path"),
        ({"agent": "outputs = ['/etc/passwd']"}, "relative path"),
        ({"agent": "outputs = ['.']"}, "relative path"),
        ({"agent": "outputs = ['tests/x.txt']"}, "under tests/"),
        ({"grader_extra": "refresh_tests = 'yes'"}, r"\[grader\] refresh_tests must be true"),
        ({"toml_extra": "[limits]\nmemory_mb = true"}, "positive number"),
        ({"toml_extra": "limits = 3"}, r"\[limits\] must be a table"),
        ({"toml_extra": "description = 3"}, "string 'description'"),
    ],
)
def test_rejects_malformed_task_toml(
    make_task: TaskFactory, kwargs: dict[str, str], message: str
) -> None:
    with pytest.raises(TaskError, match=message):
        load_task(make_task(**kwargs))


def test_rejects_non_positive_timeout(make_task: TaskFactory) -> None:
    root = make_task()
    text = (root / "task.toml").read_text().replace("timeout_sec = 30", "timeout_sec = 0", 1)
    (root / "task.toml").write_text(text)
    with pytest.raises(TaskError, match=r"\[solution\] timeout_sec must be a positive number"):
        load_task(root)


def test_rejects_missing_command(make_task: TaskFactory) -> None:
    root = make_task()
    text = (root / "task.toml").read_text().replace("[grader]\ncommand", "[grader]\ncmd")
    (root / "task.toml").write_text(text)
    with pytest.raises(TaskError, match="unknown key"):
        load_task(root)
    (root / "task.toml").write_text(text.replace('cmd = "python -m pytest -q tests"\n', ""))
    with pytest.raises(TaskError, match="needs a non-empty string 'command'"):
        load_task(root)


@pytest.mark.parametrize("missing", ["tests", "solution"])
def test_rejects_missing_directories(make_task: TaskFactory, missing: str) -> None:
    root = make_task()
    for path in sorted((root / missing).rglob("*"), reverse=True):
        path.unlink()
    (root / missing).rmdir()
    with pytest.raises(TaskError, match=f"missing {missing}/"):
        load_task(root)


def test_rejects_missing_instruction_and_bad_environment(make_task: TaskFactory) -> None:
    root = make_task()
    (root / "instruction.md").unlink()
    with pytest.raises(TaskError, match=r"missing instruction\.md"):
        load_task(root)
    (root / "instruction.md").write_text("x")
    (root / "environment" / "README.txt").unlink()
    (root / "environment").rmdir()
    assert load_task(root).environment_dir.exists() is False
    (root / "environment").write_text("not a dir")
    with pytest.raises(TaskError, match="must be a directory"):
        load_task(root)
