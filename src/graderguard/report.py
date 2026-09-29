"""Render an audit as JSON (for machines) or Markdown (for reviewers)."""

from __future__ import annotations

import json
from typing import Any

from graderguard import __version__
from graderguard.audit import Attempt, AuditReport, CheatResult, Status, Verdict
from graderguard.sandbox import CommandResult

SCHEMA_VERSION = 1
MARKDOWN_OUTPUT_LINES = 15

_VERDICT_TEXT = {
    Verdict.NO_HOLES: "NO HOLES",
    Verdict.HOLES_FOUND: "HOLES FOUND",
    Verdict.ACCEPTS_NO_WORK: "ACCEPTS NO WORK",
    Verdict.BROKEN_REFERENCE: "BROKEN REFERENCE",
}
_STATUS_TEXT = {
    Status.HOLE: "**HOLE**",
    Status.BLOCKED: "blocked",
    Status.NOT_APPLICABLE: "not applicable",
    Status.ERROR: "error",
}


def to_dict(report: AuditReport) -> dict[str, Any]:
    """A JSON-ready view of the whole audit."""
    task = report.task
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "graderguard", "version": __version__},
        "task": {
            "name": task.name,
            "path": str(task.root),
            "grader_command": task.grader_command,
            "tests_visible": task.tests_visible,
            "refresh_tests": task.refresh_tests,
            "programs": list(task.programs),
            "outputs": list(task.outputs),
        },
        "verdict": report.verdict.value,
        "summary": {
            "cheats": len(report.results),
            "holes": report.count(Status.HOLE),
            "blocked": report.count(Status.BLOCKED),
            "not_applicable": report.count(Status.NOT_APPLICABLE),
            "errors": report.count(Status.ERROR),
        },
        "baselines": {
            "reference": _attempt(report.reference),
            "empty": _attempt(report.empty) if report.empty else None,
        },
        "results": [_result(r) for r in report.results],
        "duration_s": report.duration_s,
    }


def render_json(report: AuditReport) -> str:
    return json.dumps(to_dict(report), indent=2) + "\n"


def summary_line(report: AuditReport) -> str:
    """One line for terminals and CI logs."""
    head = f"{report.task.name}: {_VERDICT_TEXT[report.verdict]}"
    if report.verdict is Verdict.BROKEN_REFERENCE:
        return f"{head} - the reference solution does not pass the grader"
    if report.verdict is Verdict.ACCEPTS_NO_WORK:
        return f"{head} - the grader passes the untouched starting workspace"
    holes = ", ".join(f"{r.cheat} ({r.severity.value})" for r in report.holes) or "none"
    return (
        f"{head} - holes: {holes}; {report.count(Status.BLOCKED)} blocked, "
        f"{report.count(Status.NOT_APPLICABLE)} not applicable, "
        f"{report.count(Status.ERROR)} errors"
    )


def render_markdown(report: AuditReport) -> str:
    task = report.task
    lines = [
        f"# GraderGuard audit: {task.name}",
        "",
        f"**Verdict: {_VERDICT_TEXT[report.verdict]}**",
        "",
        f"- Task: `{task.root}` (tests visible to the agent: {_yes(task.tests_visible)}, "
        f"restored before grading: {_yes(task.refresh_tests or not task.tests_visible)})",
        f"- Grader: `{task.grader_command}`",
        f"- Reference solution: {_baseline(report.reference)}",
    ]
    if report.empty is not None:
        lines.append(f"- Empty workspace: {_baseline(report.empty)}")
    if report.verdict is Verdict.BROKEN_REFERENCE:
        lines += ["", "The reference solution must pass before cheats mean anything.", ""]
        lines += _evidence(report.reference)
        return _join(lines)
    if report.verdict is Verdict.ACCEPTS_NO_WORK and report.empty is not None:
        lines += ["", "The grader passes a workspace where the agent did nothing.", ""]
        lines += _evidence(report.empty)
        return _join(lines)

    lines += [
        "",
        f"{len(report.holes)} of {len(report.results)} cheats were accepted by the grader.",
        "",
        "| Cheat | Severity | Result | Grader | Detail |",
        "|---|---|---|---|---|",
    ]
    for r in report.results:
        exit_text = _exit(r.attempt.grader) if r.attempt else "-"
        detail = r.reason or (r.attempt.note if r.attempt and r.attempt.note else "")
        lines.append(
            f"| {r.cheat} | {r.severity.value} | {_STATUS_TEXT[r.status]} | {exit_text} "
            f"| {_cell(detail)} |"
        )
    if report.holes:
        lines += ["", "## Holes"]
        for r in report.holes:
            lines += ["", f"### {r.cheat} ({r.severity.value})", "", r.description, ""]
            if r.attempt is not None:
                lines += _evidence(r.attempt)
    return _join(lines)


def _join(lines: list[str]) -> str:
    """Join lines, dropping repeated blank lines outside code fences and trailing ones."""
    kept: list[str] = []
    in_code = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
        elif line == "" and not in_code and (not kept or kept[-1] == ""):
            continue
        kept.append(line)
    while kept and kept[-1] == "":
        kept.pop()
    return "\n".join(kept) + "\n"


def _attempt(attempt: Attempt) -> dict[str, Any]:
    return {
        "label": attempt.label,
        "passed": attempt.passed,
        "note": attempt.note,
        "changes": [{"kind": c.kind, "path": c.path} for c in attempt.changes],
        "setup": _command(attempt.setup) if attempt.setup else None,
        "grader": _command(attempt.grader),
    }


def _result(result: CheatResult) -> dict[str, Any]:
    return {
        "cheat": result.cheat,
        "description": result.description,
        "severity": result.severity.value,
        "status": result.status.value,
        "reason": result.reason,
        "attempt": _attempt(result.attempt) if result.attempt else None,
    }


def _command(result: CommandResult) -> dict[str, Any]:
    return {
        "command": result.command,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_s": result.duration_s,
        "output": result.output,
    }


def _evidence(attempt: Attempt) -> list[str]:
    lines: list[str] = []
    if attempt.note:
        lines.append(f"- Note: {attempt.note}")
    changed = ", ".join(f"`{c.kind} {c.path}`" for c in attempt.changes) or "none"
    lines.append(f"- Files changed before grading: {changed}")
    if attempt.setup is not None:
        lines.append(f"- Solution command: `{attempt.setup.command}` -> {_exit(attempt.setup)}")
        lines += _tail(attempt.setup.output)
    lines.append(f"- Grader: `{attempt.grader.command}` -> {_exit(attempt.grader)}")
    lines += _tail(attempt.grader.output)
    return lines


def _tail(output: str) -> list[str]:
    tail = output.rstrip("\n").splitlines()[-MARKDOWN_OUTPUT_LINES:]
    if not tail:
        return []
    return ["", "```text", *tail, "```", ""]


def _baseline(attempt: Attempt) -> str:
    verdict = "passes" if attempt.passed else "fails"
    return f"{verdict} (grader {_exit(attempt.grader)})"


def _exit(result: CommandResult) -> str:
    return "timeout" if result.timed_out else f"exit {result.exit_code}"


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
