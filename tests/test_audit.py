import dataclasses
from collections.abc import Callable
from pathlib import Path

import pytest

from graderguard.audit import AuditReport, Status, Verdict, run_attempt, run_audit, run_cheat
from graderguard.cheats import APPLICABLE, Applicability, Cheat, Severity, get_cheat
from graderguard.task import Task, load_task

TaskFactory = Callable[..., Path]

# The contract the demo and README rely on: which cheats each sample grader accepts.
EXPECTED_HOLES = {
    "exit-code-only": {"exit-zero-stub", "empty-output", "conftest-force-pass"},
    "hardcodable": {"hardcode-visible-expected", "conftest-force-pass"},
    "robust": set(),
}


@pytest.mark.parametrize("sample", sorted(EXPECTED_HOLES))
def test_sample_holes_are_pinned(sample_reports: dict[str, AuditReport], sample: str) -> None:
    report = sample_reports[sample]
    assert report.reference.passed
    assert report.empty is not None
    assert not report.empty.passed
    assert {r.cheat for r in report.holes} == EXPECTED_HOLES[sample]
    assert not [r for r in report.results if r.status is Status.ERROR]
    if EXPECTED_HOLES[sample]:
        assert report.verdict is Verdict.HOLES_FOUND
        assert report.exit_code == 1
    else:
        assert report.verdict is Verdict.NO_HOLES
        assert report.exit_code == 0


def test_robust_sample_blocks_every_cheat(sample_reports: dict[str, AuditReport]) -> None:
    report = sample_reports["robust"]
    assert {r.status for r in report.results} == {Status.BLOCKED}


def test_hidden_tests_make_test_reading_cheats_not_applicable(
    sample_reports: dict[str, AuditReport],
) -> None:
    by_name = {r.cheat: r for r in sample_reports["exit-code-only"].results}
    assert by_name["hardcode-visible-expected"].status is Status.NOT_APPLICABLE
    assert by_name["gut-visible-tests"].reason == "tests are not visible to the agent"


def test_hole_evidence_records_changed_files(sample_reports: dict[str, AuditReport]) -> None:
    hole = next(r for r in sample_reports["hardcodable"].holes if r.cheat.startswith("hardcode"))
    assert hole.attempt is not None
    changed = {(c.kind, c.path) for c in hole.attempt.changes}
    assert changed == {("A", "out/summary.json"), ("A", "stats.py")}
    assert hole.attempt.grader.exit_code == 0
    assert hole.attempt.note is not None
    assert "tests/test_summary.py" in hole.attempt.note


def test_task_directory_is_never_modified(sample_reports: dict[str, AuditReport]) -> None:
    for report in sample_reports.values():
        root = report.task.root
        assert not (root / "environment" / "out").exists()
        assert not (root / "conftest.py").exists()


def test_broken_reference_stops_the_audit(make_task: TaskFactory) -> None:
    task = load_task(make_task(solution_command="echo cannot solve; exit 4"))
    report = run_audit(task)
    assert report.verdict is Verdict.BROKEN_REFERENCE
    assert report.exit_code == 3
    assert report.empty is None
    assert report.results == ()
    assert report.reference.setup is not None
    assert report.reference.setup.exit_code == 4


def test_grader_that_accepts_no_work(make_task: TaskFactory) -> None:
    task = load_task(make_task(grader_command="true"))
    messages: list[str] = []
    report = run_audit(task, progress=messages.append)
    assert report.verdict is Verdict.ACCEPTS_NO_WORK
    assert report.exit_code == 1
    assert messages == ["baseline reference: pass", "baseline empty: PASS"]


def test_unrefreshed_visible_tests_can_be_gutted(make_task: TaskFactory) -> None:
    task = load_task(
        make_task(
            agent='programs = ["main.py"]\noutputs = ["out/answer.txt"]\ntests_visible = true',
            grader_extra="refresh_tests = false",
        )
    )
    result = run_cheat(task, get_cheat("gut-visible-tests"))
    assert result.status is Status.HOLE


def test_fixture_task_blocks_stub_cheats(make_task: TaskFactory) -> None:
    task = load_task(make_task(grader_command="python -m pytest -q --noconftest tests"))
    report = run_audit(task, [get_cheat("exit-zero-stub"), get_cheat("conftest-force-pass")])
    assert report.verdict is Verdict.NO_HOLES
    assert [r.status for r in report.results] == [Status.BLOCKED, Status.BLOCKED]


class _Exploding(Cheat):
    name = "exploding"
    description = "A plugin with a bug."
    severity = Severity.LOW

    def applicable(self, task: Task) -> Applicability:
        return APPLICABLE

    def apply(self, task: Task, workspace: Path) -> str | None:
        raise RuntimeError("plugin bug")


def test_broken_plugin_is_reported_as_error(make_task: TaskFactory) -> None:
    result = run_cheat(load_task(make_task()), _Exploding())
    assert result.status is Status.ERROR
    assert result.reason == "RuntimeError: plugin bug"
    assert result.attempt is None


def test_hardcode_without_usable_literal_is_not_applicable(make_task: TaskFactory) -> None:
    task = load_task(
        make_task(
            agent='programs = ["main.py"]\noutputs = ["out/answer.txt"]\ntests_visible = true',
            files={"tests/test_answer.py": "def test_answer():\n    assert compute() > 1\n"},
            solution_command="true",
            grader_command="true",
        )
    )
    result = run_cheat(task, get_cheat("hardcode-visible-expected"))
    assert result.status is Status.NOT_APPLICABLE
    assert "no expected literal" in result.reason


def test_grader_timeout_counts_as_failure(make_task: TaskFactory) -> None:
    task = load_task(make_task(grader_command="sleep 20", grader_extra="", solution_command="true"))
    fast = dataclasses.replace(task, grader_timeout=0.3)
    attempt = run_attempt(fast, "slow", None)
    assert attempt.grader.timed_out
    assert not attempt.passed
