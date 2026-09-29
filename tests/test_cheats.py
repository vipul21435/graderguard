import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from graderguard.cheats import Cheat, NotApplicableError, Severity, all_cheats, get_cheat
from graderguard.cheats.base import is_python, write_program
from graderguard.cheats.hardcode import (
    HardcodeVisibleExpected,
    choose_expectation,
    find_expectations,
    serialize,
)
from graderguard.cheats.pytest_harness import ConftestForcePass, GutVisibleTests
from graderguard.cheats.stubs import EmptyOutput, ExitZeroStub
from graderguard.task import Task, load_task

TaskFactory = Callable[..., Path]


def _task(make_task: TaskFactory, **kwargs: str) -> Task:
    return load_task(make_task(**kwargs))


def test_registry_has_five_distinct_cheats() -> None:
    cheats = all_cheats()
    names = [c.name for c in cheats]
    assert len(names) == len(set(names)) == 5
    for cheat in cheats:
        assert isinstance(cheat, Cheat)
        assert cheat.description.strip()
        assert isinstance(cheat.severity, Severity)
    assert get_cheat("empty-output").name == "empty-output"
    with pytest.raises(KeyError):
        get_cheat("no-such-cheat")


def test_python_stub_writes_outputs_relative_to_its_own_location(tmp_path: Path) -> None:
    write_program(tmp_path, "bin/tool.py", {"out/a.txt": b"hello\n"}, "t")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    proc = subprocess.run(
        [sys.executable, str(tmp_path / "bin" / "tool.py")], cwd=elsewhere, check=False
    )
    assert proc.returncode == 0
    assert (tmp_path / "out" / "a.txt").read_bytes() == b"hello\n"
    assert os.access(tmp_path / "bin" / "tool.py", os.X_OK)


def test_shell_stub_writes_quoted_outputs(tmp_path: Path) -> None:
    write_program(tmp_path, "run.sh", {"out/it's.txt": b"a 'quoted' $HOME"}, "t")
    proc = subprocess.run(["/bin/sh", str(tmp_path / "run.sh")], cwd="/", check=False)
    assert proc.returncode == 0
    assert (tmp_path / "out" / "it's.txt").read_text() == "a 'quoted' $HOME"
    assert is_python("x/y.py")
    assert not is_python("run.sh")


def test_exit_zero_stub(make_task: TaskFactory, tmp_path: Path) -> None:
    cheat = ExitZeroStub()
    assert not cheat.applicable(_task(make_task, agent="outputs = ['o.txt']")).ok
    task = load_task(make_task(name="with-programs"))
    assert cheat.applicable(task).ok
    ws = tmp_path / "ws"
    ws.mkdir()
    assert cheat.apply(task, ws) is None
    proc = subprocess.run([sys.executable, "main.py"], cwd=ws, check=False)
    assert proc.returncode == 0
    assert not (ws / "out").exists()


def test_empty_output(make_task: TaskFactory, tmp_path: Path) -> None:
    cheat = EmptyOutput()
    assert not cheat.applicable(_task(make_task, agent="programs = ['main.py']")).ok
    task = load_task(make_task(name="with-outputs"))
    assert cheat.applicable(task).ok
    ws = tmp_path / "ws"
    ws.mkdir()
    cheat.apply(task, ws)
    (ws / "out" / "answer.txt").unlink()
    subprocess.run([sys.executable, "main.py"], cwd=ws, check=True)
    assert (ws / "out" / "answer.txt").read_bytes() == b""


def _tests(ws: Path, source: str) -> None:
    (ws / "tests").mkdir(parents=True, exist_ok=True)
    (ws / "tests" / "test_x.py").write_text(source)


def test_find_expectations_resolves_constants_and_inline_literals(tmp_path: Path) -> None:
    _tests(
        tmp_path,
        "EXPECTED: dict = {'a': 1}\nLIMIT = 3\nX, Y = 1, 2\nNOT_LITERAL = len('ab')\n"
        "def helper():\n    assert 1 == 1\n"
        "def test_one():\n    got = read('out/r.json')\n    assert got == EXPECTED\n"
        "    assert 'fixed' == got\n    assert got == NOT_LITERAL\n    assert got != 'no'\n"
        "    assert got == True\n    assert got\n"
        "class TestGroup:\n    async def test_two(self):\n        assert run() == [1, 2]\n",
    )
    (tmp_path / "tests" / "test_broken.py").write_text("def test_(:\n")
    found = find_expectations(tmp_path)
    assert [e.value for e in found] == [{"a": 1}, "fixed", [1, 2]]
    assert found[0].source == "tests/test_x.py:9"
    assert "out/r.json" in found[0].strings


def test_choose_expectation_prefers_mentions_then_containers(tmp_path: Path) -> None:
    _tests(
        tmp_path,
        "def test_a():\n    assert count() == 42\n    assert name() == 'x'\n"
        "def test_b():\n    assert read('data/b.txt') == 'bee'\n",
    )
    found = find_expectations(tmp_path)
    b = choose_expectation("data/b.txt", found, only_output=False)
    assert b is not None
    assert b.value == "bee"
    only = choose_expectation("other.txt", found, only_output=True)
    assert only is not None
    assert only.value == "x"
    assert choose_expectation("other.txt", found, only_output=False) is None


@pytest.mark.parametrize(
    ("value", "output", "expected"),
    [
        (b"raw", "a.bin", b"raw"),
        ("text", "a.json", b"text"),
        ({"k": [1, 2]}, "a.json", b'{\n  "k": [\n    1,\n    2\n  ]\n}\n'),
        ({1, 2}, "a.json", None),
        (["x", 2], "a.txt", b"x\n2\n"),
        (42, "a.txt", b"42\n"),
    ],
)
def test_serialize(value: object, output: str, expected: bytes | None) -> None:
    assert serialize(value, output) == expected


def test_hardcode_applicability_and_apply(make_task: TaskFactory, tmp_path: Path) -> None:
    cheat = HardcodeVisibleExpected()
    assert not cheat.applicable(_task(make_task)).ok
    no_outputs = _task(make_task, name="n", agent="tests_visible = true")
    assert "no outputs" in cheat.applicable(no_outputs).reason
    task = _task(
        make_task,
        name="v",
        agent='programs = ["main.py"]\noutputs = ["out/answer.txt"]\ntests_visible = true',
    )
    assert cheat.applicable(task).ok
    ws = tmp_path / "ws"
    _tests(ws, "def test_a():\n    assert open('out/answer.txt').read() == '42\\n'\n")
    note = cheat.apply(task, ws)
    assert note == "copied out/answer.txt <- tests/test_x.py:2"
    assert (ws / "out" / "answer.txt").read_text() == "42\n"
    (ws / "out" / "answer.txt").unlink()
    subprocess.run([sys.executable, "main.py"], cwd=ws, check=True)
    assert (ws / "out" / "answer.txt").read_text() == "42\n"
    _tests(ws, "def test_a():\n    assert compute() > 1\n")
    with pytest.raises(NotApplicableError, match="no expected literal"):
        cheat.apply(task, ws)


def test_conftest_force_pass(make_task: TaskFactory, tmp_path: Path) -> None:
    cheat = ConftestForcePass()
    assert not cheat.applicable(_task(make_task, grader_command="sh tests/check.sh")).ok
    task = _task(make_task, name="p")
    assert cheat.applicable(task).ok
    cheat.apply(task, tmp_path)
    assert "pytest_runtest_makereport" in (tmp_path / "conftest.py").read_text()


def test_gut_visible_tests(make_task: TaskFactory, tmp_path: Path) -> None:
    cheat = GutVisibleTests()
    assert not cheat.applicable(_task(make_task)).ok
    task = _task(make_task, name="g", agent="tests_visible = true")
    assert cheat.applicable(task).ok
    _tests(tmp_path, "def test_a():\n    assert False\n\n\ndef helper():\n    return 1\n")
    (tmp_path / "tests" / "test_bad.py").write_text("def test_(:\n")
    assert cheat.apply(task, tmp_path) == "emptied 1 test function(s)"
    text = (tmp_path / "tests" / "test_x.py").read_text()
    assert "assert" not in text
    assert "return 1" in text
    _tests(tmp_path, "def helper():\n    return 1\n")
    with pytest.raises(NotApplicableError, match="no test functions"):
        cheat.apply(task, tmp_path)
