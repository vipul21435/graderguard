"""The cheat plugin interface and helpers shared by the built-in cheats.

A cheat simulates one lazy or adversarial agent strategy. The audit runs each applicable cheat
in its own fresh workspace instead of the reference solution, then runs the task's grader. If
the grader passes, the cheat found a hole.

``applicable`` answers from the auditor's side (it may read the task metadata); ``apply`` plays
the agent and must only read and write inside the workspace it is given.
"""

from __future__ import annotations

import stat
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from graderguard.task import Task

PYTHON_SUFFIXES = frozenset({".py"})


class Severity(StrEnum):
    """How bad it is when a grader accepts this cheat."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Applicability:
    ok: bool
    reason: str = ""


APPLICABLE = Applicability(ok=True)


class NotApplicableError(Exception):
    """Raised by ``apply`` when the workspace offers nothing for this cheat to use."""


class Cheat(ABC):
    """Base class for cheat plugins. Subclasses set the three class attributes."""

    name: str
    description: str
    severity: Severity

    @abstractmethod
    def applicable(self, task: Task) -> Applicability:
        """Whether this cheat makes sense for ``task`` at all."""

    @abstractmethod
    def apply(self, task: Task, workspace: Path) -> str | None:
        """Change ``workspace`` the way the lazy agent would, instead of solving the task.

        May return a short note for the report (for example where a copied value came from).
        """


def is_python(rel_path: str) -> bool:
    return PurePosixPath(rel_path).suffix in PYTHON_SUFFIXES


def write_file(workspace: Path, rel_path: str, data: bytes) -> None:
    path = workspace / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_program(workspace: Path, rel_path: str, outputs: dict[str, bytes], tag: str) -> None:
    """Write a program at ``rel_path`` that writes ``outputs`` and exits 0.

    Output paths are workspace-relative and resolved from the program's own location, so the
    stub works no matter which directory the grader runs it from. Python programs get a Python
    stub; anything else gets a POSIX shell stub.
    """
    depth = len(PurePosixPath(rel_path).parts) - 1
    if is_python(rel_path):
        body = (
            f"# graderguard cheat: {tag}\n"
            "import pathlib\n\n"
            f"_ROOT = pathlib.Path(__file__).resolve().parents[{depth}]\n"
            f"for _rel, _data in {outputs!r}.items():\n"
            "    _path = _ROOT / _rel\n"
            "    _path.parent.mkdir(parents=True, exist_ok=True)\n"
            "    _path.write_bytes(_data)\n"
            "raise SystemExit(0)\n"
        )
    else:
        up = "/".join([".."] * depth) or "."
        lines = [
            "#!/bin/sh",
            f"# graderguard cheat: {tag}",
            f'cd "$(dirname "$0")/{up}" || exit 0',
        ]
        for rel, data in outputs.items():
            parent = str(PurePosixPath(rel).parent)
            lines.append(f"mkdir -p {_sh_quote(parent)}")
            text = _sh_quote(data.decode("utf-8", "replace"))
            lines.append(f"printf '%s' {text} > {_sh_quote(rel)}")
        lines.append("exit 0")
        body = "\n".join(lines) + "\n"
    write_file(workspace, rel_path, body.encode())
    path = workspace / rel_path
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _sh_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"
