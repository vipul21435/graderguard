import runpy
import subprocess
import sys

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
