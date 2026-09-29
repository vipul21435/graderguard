"""Shared fixtures: a builder for small throwaway tasks in the documented layout."""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples" / "tasks"

TaskFactory = Callable[..., Path]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


@pytest.fixture
def make_task(tmp_path: Path) -> TaskFactory:
    """Build a task directory from a few strings; returns its path."""

    def build(
        *,
        name: str = "fixture-task",
        toml_extra: str = "",
        agent: str = 'programs = ["main.py"]\noutputs = ["out/answer.txt"]',
        solution_command: str = 'cp "$GG_SOLUTION_DIR/main.py" main.py',
        grader_command: str = "python -m pytest -q tests",
        grader_extra: str = "",
        files: dict[str, str] | None = None,
    ) -> Path:
        root = tmp_path / name
        toml = (
            f'name = "{name}"\n{toml_extra}\n'
            f"[agent]\n{agent}\n\n"
            f"[solution]\ncommand = '{solution_command}'\ntimeout_sec = 30\n\n"
            f'[grader]\ncommand = "{grader_command}"\ntimeout_sec = 30\n{grader_extra}\n'
        )
        _write(root / "task.toml", toml)
        _write(root / "instruction.md", "Write main.py that writes 42 to out/answer.txt.\n")
        default_files = {
            "solution/main.py": """
                from pathlib import Path

                Path("out").mkdir(exist_ok=True)
                Path("out/answer.txt").write_text(str(6 * 7) + "\\n")
            """,
            "tests/test_answer.py": """
                import subprocess
                import sys
                from pathlib import Path


                def test_answer():
                    subprocess.run([sys.executable, "main.py"], check=True)
                    assert Path("out/answer.txt").read_text() == "42\\n"
            """,
            "environment/README.txt": "starting workspace\n",
        }
        for rel, text in {**default_files, **(files or {})}.items():
            _write(root / rel, text)
        return root

    return build
