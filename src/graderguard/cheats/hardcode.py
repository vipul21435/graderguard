"""Copy expected values out of visible test files and replay them as the output."""

from __future__ import annotations

import ast
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from graderguard.cheats.base import (
    Applicability,
    Cheat,
    NotApplicableError,
    Severity,
    write_file,
    write_program,
)
from graderguard.task import Task

_MISSING = object()


@dataclass(frozen=True)
class Expectation:
    """A literal a visible test compares against, with where it was found."""

    value: object
    source: str
    strings: frozenset[str]


def find_expectations(workspace: Path) -> list[Expectation]:
    """Collect literal operands of ``assert a == b`` in visible test functions.

    Names bound to a literal at module level (``EXPECTED = {...}``) are resolved too. Each
    expectation remembers the string constants of its test function, which is how it is
    matched to an output path later.
    """
    found: list[Expectation] = []
    tests_dir = workspace / "tests"
    for path in sorted(tests_dir.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        constants = _module_constants(tree)
        rel = path.relative_to(workspace).as_posix()
        for func in _test_functions(tree):
            strings = frozenset(
                node.value
                for node in ast.walk(func)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            )
            for node in ast.walk(func):
                if not (
                    isinstance(node, ast.Assert)
                    and isinstance(node.test, ast.Compare)
                    and len(node.test.ops) == 1
                    and isinstance(node.test.ops[0], ast.Eq)
                ):
                    continue
                for side in (node.test.left, node.test.comparators[0]):
                    value = _literal(side, constants)
                    if value is not _MISSING and _useful(value):
                        found.append(Expectation(value, f"{rel}:{node.lineno}", strings))
    return found


def choose_expectation(
    output: str, expectations: list[Expectation], *, only_output: bool
) -> Expectation | None:
    """Pick the expectation most likely to be the content of ``output``.

    Prefer expectations whose test function mentions the output path; when the task has a
    single output, any expectation will do. Containers and strings beat bare numbers.
    """
    name = PurePosixPath(output).name
    mentioned = [
        exp
        for exp in expectations
        if any(s in (output, name) or s.endswith("/" + name) for s in exp.strings)
    ]
    pool = mentioned or (expectations if only_output else [])
    if not pool:
        return None
    return min(pool, key=_rank)


def serialize(value: object, output: str) -> bytes | None:
    """Render ``value`` the way a test reading ``output`` most likely parses it."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode()
    if PurePosixPath(output).suffix == ".json":
        try:
            return (json.dumps(value, indent=2) + "\n").encode()
        except (TypeError, ValueError):
            return None
    if isinstance(value, list | tuple):
        return ("\n".join(str(item) for item in value) + "\n").encode()
    return f"{value}\n".encode()


class HardcodeVisibleExpected(Cheat):
    name = "hardcode-visible-expected"
    description = (
        "Read the expected values out of the visible tests and write them straight into the "
        "outputs, from programs that replay them without reading any input."
    )
    severity = Severity.HIGH

    def applicable(self, task: Task) -> Applicability:
        if not task.tests_visible:
            return Applicability(False, "tests are not visible to the agent")
        if not task.outputs:
            return Applicability(False, "the task declares no outputs")
        return Applicability(True)

    def apply(self, task: Task, workspace: Path) -> str | None:
        expectations = find_expectations(workspace)
        outputs: dict[str, bytes] = {}
        notes: list[str] = []
        for rel in task.outputs:
            exp = choose_expectation(rel, expectations, only_output=len(task.outputs) == 1)
            data = serialize(exp.value, rel) if exp else None
            if exp is None or data is None:
                continue
            outputs[rel] = data
            notes.append(f"{rel} <- {exp.source}")
        if not outputs:
            raise NotApplicableError("no expected literal in the visible tests fits an output")
        for rel, data in outputs.items():
            write_file(workspace, rel, data)
        for program in task.programs:
            write_program(workspace, program, outputs, self.name)
        return "copied " + ", ".join(notes)


def _test_functions(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test"
        ):
            yield node


def _module_constants(tree: ast.Module) -> dict[str, object]:
    constants: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value_node = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value_node = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name):
            value = _literal(value_node, {})
            if value is not _MISSING:
                constants[target.id] = value
    return constants


def _literal(node: ast.expr, constants: dict[str, object]) -> object:
    if isinstance(node, ast.Name):
        return constants.get(node.id, _MISSING)
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return _MISSING


def _useful(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str | bytes | list | tuple | dict | set):
        return len(value) > 0
    return isinstance(value, int | float)


def _rank(exp: Expectation) -> int:
    return 1 if isinstance(exp.value, int | float) else 0
