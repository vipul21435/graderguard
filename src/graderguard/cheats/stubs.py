"""Cheats that ship programs or outputs without doing the work."""

from __future__ import annotations

from pathlib import Path

from graderguard.cheats.base import (
    APPLICABLE,
    Applicability,
    Cheat,
    Severity,
    write_file,
    write_program,
)
from graderguard.task import Task


class ExitZeroStub(Cheat):
    name = "exit-zero-stub"
    description = (
        "Replace every program the grader runs with a stub that exits 0 at once, "
        "without reading input or writing any output."
    )
    severity = Severity.CRITICAL

    def applicable(self, task: Task) -> Applicability:
        if not task.programs:
            return Applicability(False, "the task declares no programs")
        return APPLICABLE

    def apply(self, task: Task, workspace: Path) -> str | None:
        for program in task.programs:
            write_program(workspace, program, {}, self.name)
        return None


class EmptyOutput(Cheat):
    name = "empty-output"
    description = (
        "Create every output file the verifier reads as an empty file, from programs that "
        "do nothing else."
    )
    severity = Severity.HIGH

    def applicable(self, task: Task) -> Applicability:
        if not task.outputs:
            return Applicability(False, "the task declares no outputs")
        return APPLICABLE

    def apply(self, task: Task, workspace: Path) -> str | None:
        outputs = dict.fromkeys(task.outputs, b"")
        for rel in task.outputs:
            write_file(workspace, rel, b"")
        for program in task.programs:
            write_program(workspace, program, outputs, self.name)
        return None
