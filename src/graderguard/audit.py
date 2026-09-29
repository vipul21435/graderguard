"""Run the baselines and every cheat against a task's grader and collect the verdicts.

Order of work:

1. Reference baseline: run the reference solution in a fresh workspace, then the grader. It
   must pass, otherwise the task is broken and nothing else is meaningful.
2. Empty baseline: grade the untouched starting workspace. It must fail, otherwise the grader
   accepts no work at all, which is the worst hole there is.
3. Each applicable cheat runs in its own fresh workspace instead of the solution. A cheat the
   grader accepts is a hole.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from graderguard.cheats import Cheat, NotApplicableError, Severity, all_cheats
from graderguard.sandbox import (
    CommandResult,
    FileChange,
    Sandbox,
    diff_snapshots,
    install_tests,
    run_command,
    sandbox_for,
    snapshot,
)
from graderguard.task import Task

Progress = Callable[[str], None]
Prepare = Callable[[Sandbox], tuple[CommandResult | None, str | None]]


class Status(StrEnum):
    HOLE = "hole"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"


class Verdict(StrEnum):
    NO_HOLES = "no_holes"
    HOLES_FOUND = "holes_found"
    ACCEPTS_NO_WORK = "accepts_no_work"
    BROKEN_REFERENCE = "broken_reference"


EXIT_CODES = {
    Verdict.NO_HOLES: 0,
    Verdict.HOLES_FOUND: 1,
    Verdict.ACCEPTS_NO_WORK: 1,
    Verdict.BROKEN_REFERENCE: 3,
}


@dataclass(frozen=True)
class Attempt:
    """One graded workspace: what was changed before grading and what the grader said."""

    label: str
    grader: CommandResult
    changes: tuple[FileChange, ...]
    setup: CommandResult | None = None
    note: str | None = None

    @property
    def passed(self) -> bool:
        setup_ok = self.setup is None or self.setup.succeeded
        return setup_ok and self.grader.succeeded


@dataclass(frozen=True)
class CheatResult:
    cheat: str
    description: str
    severity: Severity
    status: Status
    reason: str = ""
    attempt: Attempt | None = None


@dataclass(frozen=True)
class AuditReport:
    task: Task
    verdict: Verdict
    reference: Attempt
    empty: Attempt | None
    results: tuple[CheatResult, ...]
    duration_s: float

    @property
    def holes(self) -> list[CheatResult]:
        return [r for r in self.results if r.status is Status.HOLE]

    def count(self, status: Status) -> int:
        return sum(1 for r in self.results if r.status is status)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.verdict]


def run_attempt(task: Task, label: str, prepare: Prepare | None) -> Attempt:
    """Prepare a fresh workspace, install the grader's tests and run the grader once."""
    with sandbox_for(task) as box:
        before = snapshot(box.workspace)
        setup, note = prepare(box) if prepare else (None, None)
        changes = tuple(diff_snapshots(before, snapshot(box.workspace)))
        install_tests(task, box.workspace)
        grader = run_command(
            task.grader_command,
            cwd=box.workspace,
            env=box.env,
            timeout=task.grader_timeout,
            memory_mb=task.memory_mb,
        )
    return Attempt(label=label, grader=grader, changes=changes, setup=setup, note=note)


def _reference(task: Task) -> Prepare:
    def prepare(box: Sandbox) -> tuple[CommandResult | None, str | None]:
        solution = box.root / "solution"
        shutil.copytree(task.solution_dir, solution, symlinks=True)
        env = box.env | {"GG_SOLUTION_DIR": str(solution)}
        result = run_command(
            task.solution_command,
            cwd=box.workspace,
            env=env,
            timeout=task.solution_timeout,
            memory_mb=task.memory_mb,
        )
        return result, None

    return prepare


def _cheat(task: Task, cheat: Cheat) -> Prepare:
    def prepare(box: Sandbox) -> tuple[CommandResult | None, str | None]:
        return None, cheat.apply(task, box.workspace)

    return prepare


def run_cheat(task: Task, cheat: Cheat) -> CheatResult:
    """Try one cheat against the task's grader."""

    def result(status: Status, reason: str = "", attempt: Attempt | None = None) -> CheatResult:
        return CheatResult(cheat.name, cheat.description, cheat.severity, status, reason, attempt)

    applicability = cheat.applicable(task)
    if not applicability.ok:
        return result(Status.NOT_APPLICABLE, applicability.reason)
    try:
        attempt = run_attempt(task, cheat.name, _cheat(task, cheat))
    except NotApplicableError as exc:
        return result(Status.NOT_APPLICABLE, str(exc))
    except Exception as exc:  # a broken plugin must not abort the whole audit
        return result(Status.ERROR, f"{type(exc).__name__}: {exc}")
    return result(Status.HOLE if attempt.passed else Status.BLOCKED, attempt=attempt)


def run_audit(
    task: Task, cheats: Sequence[Cheat] | None = None, progress: Progress | None = None
) -> AuditReport:
    """Audit ``task``'s grader: two baselines, then every cheat in ``cheats``."""
    say = progress or (lambda _msg: None)
    start = time.monotonic()
    chosen = list(cheats) if cheats is not None else all_cheats()

    def done(verdict: Verdict, empty: Attempt | None, results: list[CheatResult]) -> AuditReport:
        elapsed = round(time.monotonic() - start, 3)
        return AuditReport(task, verdict, reference, empty, tuple(results), elapsed)

    reference = run_attempt(task, "reference", _reference(task))
    say(f"baseline reference: {'pass' if reference.passed else 'FAIL'}")
    if not reference.passed:
        return done(Verdict.BROKEN_REFERENCE, None, [])
    empty = run_attempt(task, "empty", None)
    say(f"baseline empty: {'PASS' if empty.passed else 'fail'}")
    if empty.passed:
        return done(Verdict.ACCEPTS_NO_WORK, empty, [])
    results: list[CheatResult] = []
    for cheat in chosen:
        result = run_cheat(task, cheat)
        say(f"{cheat.name}: {result.status.value}")
        results.append(result)
    verdict = (
        Verdict.HOLES_FOUND if any(r.status is Status.HOLE for r in results) else (Verdict.NO_HOLES)
    )
    return done(verdict, empty, results)
