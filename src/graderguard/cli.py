"""Command-line entry point for GraderGuard."""

from __future__ import annotations

from typing import Annotated

import typer

from graderguard import __version__

app = typer.Typer(
    name="graderguard",
    help="Audit benchmark-task graders for reward hacking before the tasks ship.",
    no_args_is_help=True,
    add_completion=False,
)


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
