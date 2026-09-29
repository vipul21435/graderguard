"""Command-line entry point for GraderGuard."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from graderguard import __version__
from graderguard.audit import run_audit
from graderguard.cheats import Cheat, all_cheats
from graderguard.report import render_json, render_markdown, summary_line
from graderguard.task import TaskError, load_task

USAGE_ERROR = 2

app = typer.Typer(
    name="graderguard",
    help="Audit benchmark-task graders for reward hacking before the tasks ship.",
    no_args_is_help=True,
    add_completion=False,
)


class ReportFormat(StrEnum):
    MD = "md"
    JSON = "json"


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"graderguard {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Print the version and exit.",
        ),
    ] = False,
) -> None:
    """Audit benchmark-task graders for reward hacking before the tasks ship."""


@app.command("version")
def version_cmd() -> None:
    """Print the installed GraderGuard version."""
    typer.echo(f"graderguard {__version__}")


@app.command("audit")
def audit_cmd(
    task_dir: Annotated[Path, typer.Argument(help="Task directory containing task.toml.")],
    fmt: Annotated[
        ReportFormat, typer.Option("--format", "-f", help="Report format.")
    ] = ReportFormat.MD,
    out: Annotated[
        Path | None,
        typer.Option("--out", "-o", help="Write the report here instead of stdout."),
    ] = None,
    cheat: Annotated[
        list[str] | None,
        typer.Option("--cheat", "-c", help="Only run this cheat (repeatable)."),
    ] = None,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Do not print progress to stderr.")
    ] = False,
) -> None:
    """Run the cheat library against TASK_DIR's grader and report every hole.

    Exit status: 0 no holes, 1 holes found (or the grader accepts no work),
    2 usage or task-layout error, 3 the reference solution fails its own grader.
    """
    try:
        task = load_task(task_dir)
    except TaskError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(USAGE_ERROR) from exc
    cheats = _select(cheat or [])

    def progress(message: str) -> None:
        if not quiet:
            typer.echo(f"  {message}", err=True)

    if not quiet:
        typer.echo(f"auditing {task.name} ({task_dir})", err=True)
    report = run_audit(task, cheats, progress)
    text = render_json(report) if fmt is ReportFormat.JSON else render_markdown(report)
    if out is None:
        typer.echo(text, nl=False)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    typer.echo(summary_line(report), err=True)
    raise typer.Exit(report.exit_code)


def _select(names: list[str]) -> list[Cheat]:
    available = all_cheats()
    if not names:
        return available
    by_name = {c.name: c for c in available}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        known = ", ".join(sorted(by_name))
        typer.echo(f"error: unknown cheat(s): {', '.join(unknown)}; known: {known}", err=True)
        raise typer.Exit(USAGE_ERROR)
    return [by_name[n] for n in names]
