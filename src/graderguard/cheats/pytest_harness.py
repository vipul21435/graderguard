"""Cheats that attack the pytest harness instead of the task."""

from __future__ import annotations

import ast
from pathlib import Path

from graderguard.cheats.base import (
    APPLICABLE,
    Applicability,
    Cheat,
    NotApplicableError,
    Severity,
    write_file,
)
from graderguard.task import Task

CONFTEST_SOURCE = """\
# graderguard cheat: conftest-force-pass
import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        report.outcome = "passed"
        report.longrepr = None
"""


class ConftestForcePass(Cheat):
    name = "conftest-force-pass"
    description = (
        "Do no work; add a conftest.py at the workspace root whose report hook rewrites "
        "every failing test phase to passed."
    )
    severity = Severity.CRITICAL

    def applicable(self, task: Task) -> Applicability:
        if not task.uses_pytest:
            return Applicability(False, "the grader command does not run pytest")
        return APPLICABLE

    def apply(self, task: Task, workspace: Path) -> str | None:
        write_file(workspace, "conftest.py", CONFTEST_SOURCE.encode())
        return None


class GutVisibleTests(Cheat):
    name = "gut-visible-tests"
    description = (
        "Do no work; edit the visible test files so every test function body is just `pass`."
    )
    severity = Severity.CRITICAL

    def applicable(self, task: Task) -> Applicability:
        if not task.tests_visible:
            return Applicability(False, "tests are not visible to the agent")
        return APPLICABLE

    def apply(self, task: Task, workspace: Path) -> str | None:
        gutted = 0
        for path in sorted((workspace / "tests").rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            count = 0
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and (
                    node.name.startswith("test")
                ):
                    node.body = [ast.Pass()]
                    count += 1
            if count:
                path.write_text(ast.unparse(ast.fix_missing_locations(tree)) + "\n")
                gutted += count
        if not gutted:
            raise NotApplicableError("no test functions found in the visible tests")
        return f"emptied {gutted} test function(s)"
