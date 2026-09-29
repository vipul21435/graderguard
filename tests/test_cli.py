import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from graderguard import __version__
from graderguard.cli import app

runner = CliRunner()


def test_version_command_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"graderguard {__version__}"


def test_version_flag_matches_version_command() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"graderguard {__version__}"


def test_no_arguments_shows_help() -> None:
    result = runner.invoke(app, [])
    assert "Usage" in result.output
    assert "version" in result.output


def test_module_entry_point_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "graderguard", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == f"graderguard {__version__}"


def test_module_entry_point_in_process(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["graderguard", "version"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("graderguard", run_name="__main__")
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"graderguard {__version__}"


EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "tasks"


def test_audit_writes_markdown_and_exits_one_on_holes(tmp_path: Path) -> None:
    out = tmp_path / "reports" / "r.md"
    result = runner.invoke(
        app, ["audit", str(EXAMPLES / "hardcodable"), "--out", str(out), "-c", "empty-output"]
    )
    assert result.exit_code == 0
    assert out.read_text().startswith("# GraderGuard audit: sensor-means")
    assert "sensor-means: NO HOLES" in result.stderr
    assert "baseline reference: pass" in result.stderr
    assert result.stdout == ""


def test_audit_json_to_stdout_quiet(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["audit", str(EXAMPLES / "exit-code-only"), "-f", "json", "-q", "-c", "exit-zero-stub"],
    )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["verdict"] == "holes_found"
    assert "auditing" not in result.stderr
    assert "HOLES FOUND" in result.stderr


def test_audit_rejects_unknown_cheat_and_bad_task(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit", str(EXAMPLES / "robust"), "--cheat", "nope"])
    assert result.exit_code == 2
    assert "unknown cheat(s): nope" in result.stderr
    result = runner.invoke(app, ["audit", str(tmp_path)])
    assert result.exit_code == 2
    assert "missing task.toml" in result.stderr
