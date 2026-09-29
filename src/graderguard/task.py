"""Load and validate a benchmark task in the documented GraderGuard layout.

A task directory looks like this::

    my-task/
      task.toml         # metadata, commands and limits (schema below)
      instruction.md    # what the agent is asked to do
      environment/      # the agent's starting workspace (optional)
      solution/         # the reference solution
      tests/            # the grader's tests

``task.toml``::

    name = "sensor-means"
    description = "optional one-liner"

    [agent]
    programs = ["stats.py"]            # files the agent writes that the grader executes
    outputs = ["out/summary.json"]     # files the verifier reads
    tests_visible = false              # copy tests/ into the workspace for the agent

    [solution]
    command = 'cp "$GG_SOLUTION_DIR/stats.py" stats.py'
    timeout_sec = 60

    [grader]
    command = "python -m pytest -q tests"
    timeout_sec = 60
    refresh_tests = true               # restore pristine tests/ right before grading

    [limits]
    memory_mb = 2048                   # address-space limit, enforced on Linux only
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

TASK_FILE = "task.toml"
DEFAULT_TIMEOUT_SEC = 60.0
DEFAULT_MEMORY_MB = 2048

_TOP_KEYS = {"name", "description", "agent", "solution", "grader", "limits"}
_AGENT_KEYS = {"programs", "outputs", "tests_visible"}
_SOLUTION_KEYS = {"command", "timeout_sec"}
_GRADER_KEYS = {"command", "timeout_sec", "refresh_tests"}
_LIMIT_KEYS = {"memory_mb"}


class TaskError(ValueError):
    """Raised when a task directory does not follow the documented layout."""


@dataclass(frozen=True)
class Task:
    """A validated task. Paths in ``programs`` and ``outputs`` are workspace-relative."""

    root: Path
    name: str
    description: str
    instruction: str
    programs: tuple[str, ...]
    outputs: tuple[str, ...]
    tests_visible: bool
    solution_command: str
    solution_timeout: float
    grader_command: str
    grader_timeout: float
    refresh_tests: bool
    memory_mb: int

    @property
    def environment_dir(self) -> Path:
        return self.root / "environment"

    @property
    def solution_dir(self) -> Path:
        return self.root / "solution"

    @property
    def tests_dir(self) -> Path:
        return self.root / "tests"

    @property
    def uses_pytest(self) -> bool:
        """True when the grader probably runs pytest.

        Either the command names pytest, or it is a wrapper (such as ``sh tests/run.sh``) and
        ``tests/`` holds pytest-style ``test_*.py`` or ``*_test.py`` files.
        """
        if "pytest" in self.grader_command:
            return True
        return any(self.tests_dir.rglob("test_*.py")) or any(self.tests_dir.rglob("*_test.py"))


def load_task(path: Path | str) -> Task:
    """Read ``task.toml`` under ``path`` and check the directory layout."""
    root = Path(path)
    if not root.is_dir():
        raise TaskError(f"{root}: not a directory")
    toml_path = root / TASK_FILE
    if not toml_path.is_file():
        raise TaskError(f"{root}: missing {TASK_FILE}")
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise TaskError(f"{toml_path}: invalid TOML: {exc}") from exc

    _reject_unknown(data, _TOP_KEYS, "top level")
    agent = _table(data, "agent", _AGENT_KEYS)
    solution = _table(data, "solution", _SOLUTION_KEYS)
    grader = _table(data, "grader", _GRADER_KEYS)
    limits = _table(data, "limits", _LIMIT_KEYS)

    for sub in ("solution", "tests"):
        if not (root / sub).is_dir():
            raise TaskError(f"{root}: missing {sub}/ directory")
    env_dir = root / "environment"
    if env_dir.exists() and not env_dir.is_dir():
        raise TaskError(f"{root}: environment must be a directory")
    instruction_path = root / "instruction.md"
    if not instruction_path.is_file():
        raise TaskError(f"{root}: missing instruction.md")

    return Task(
        root=root,
        name=_string(data, "name", "top level", required=True),
        description=_string(data, "description", "top level", required=False),
        instruction=instruction_path.read_text(encoding="utf-8"),
        programs=_paths(agent, "programs"),
        outputs=_paths(agent, "outputs"),
        tests_visible=_bool(agent, "tests_visible", "agent", default=False),
        solution_command=_string(solution, "command", "solution", required=True),
        solution_timeout=_positive(solution, "timeout_sec", "solution", DEFAULT_TIMEOUT_SEC),
        grader_command=_string(grader, "command", "grader", required=True),
        grader_timeout=_positive(grader, "timeout_sec", "grader", DEFAULT_TIMEOUT_SEC),
        refresh_tests=_bool(grader, "refresh_tests", "grader", default=True),
        memory_mb=int(_positive(limits, "memory_mb", "limits", DEFAULT_MEMORY_MB)),
    )


def _reject_unknown(table: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise TaskError(f"{TASK_FILE}: unknown key(s) in {where}: {', '.join(unknown)}")


def _table(data: dict[str, Any], key: str, allowed: set[str]) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise TaskError(f"{TASK_FILE}: [{key}] must be a table")
    _reject_unknown(value, allowed, f"[{key}]")
    return value


def _string(table: dict[str, Any], key: str, where: str, *, required: bool) -> str:
    value = table.get(key)
    if value is None:
        if required:
            raise TaskError(f"{TASK_FILE}: {where} needs a non-empty string '{key}'")
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise TaskError(f"{TASK_FILE}: {where} needs a non-empty string '{key}'")
    return value


def _bool(table: dict[str, Any], key: str, where: str, *, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise TaskError(f"{TASK_FILE}: [{where}] {key} must be true or false")
    return value


def _positive(table: dict[str, Any], key: str, where: str, default: float) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise TaskError(f"{TASK_FILE}: [{where}] {key} must be a positive number")
    return float(value)


def _paths(table: dict[str, Any], key: str) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TaskError(f"{TASK_FILE}: [agent] {key} must be a list of strings")
    cleaned: list[str] = []
    for item in value:
        pure = PurePosixPath(item)
        if not pure.parts or pure.is_absolute() or ".." in pure.parts or "\\" in item:
            raise TaskError(f"{TASK_FILE}: [agent] {key} entry {item!r} must be a relative path")
        if pure.parts[0] == "tests":
            raise TaskError(f"{TASK_FILE}: [agent] {key} entry {item!r} must not be under tests/")
        cleaned.append(pure.as_posix())
    return tuple(cleaned)
