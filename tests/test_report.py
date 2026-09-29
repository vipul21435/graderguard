import json
from collections.abc import Callable
from pathlib import Path

from graderguard.audit import AuditReport, run_audit
from graderguard.report import (
    SCHEMA_VERSION,
    _join,
    render_json,
    render_markdown,
    summary_line,
    to_dict,
)
from graderguard.task import load_task

TaskFactory = Callable[..., Path]


def test_json_report_structure(sample_reports: dict[str, AuditReport]) -> None:
    data = json.loads(render_json(sample_reports["hardcodable"]))
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["tool"]["name"] == "graderguard"
    assert data["task"]["name"] == "sensor-means"
    assert data["verdict"] == "holes_found"
    assert data["summary"] == {
        "cheats": 5,
        "holes": 2,
        "blocked": 3,
        "not_applicable": 0,
        "errors": 0,
    }
    assert data["baselines"]["reference"]["passed"] is True
    assert data["baselines"]["reference"]["setup"]["exit_code"] == 0
    assert data["baselines"]["empty"]["passed"] is False
    holes = [r for r in data["results"] if r["status"] == "hole"]
    assert {h["cheat"] for h in holes} == {"hardcode-visible-expected", "conftest-force-pass"}
    assert all(h["attempt"]["grader"]["exit_code"] == 0 for h in holes)


def test_markdown_report_lists_every_cheat_and_hole(
    sample_reports: dict[str, AuditReport],
) -> None:
    text = render_markdown(sample_reports["exit-code-only"])
    assert text.startswith("# GraderGuard audit: normalize-names\n")
    assert "**Verdict: HOLES FOUND**" in text
    assert "| exit-zero-stub | critical | **HOLE** | exit 0 |" in text
    assert "| gut-visible-tests | critical | not applicable | - |" in text
    assert "### conftest-force-pass (critical)" in text
    assert "\n\n\n" not in text


def test_markdown_for_clean_grader_has_no_holes_section(
    sample_reports: dict[str, AuditReport],
) -> None:
    text = render_markdown(sample_reports["robust"])
    assert "**Verdict: NO HOLES**" in text
    assert "0 of 5 cheats were accepted" in text
    assert "## Holes" not in text


def test_summary_lines(sample_reports: dict[str, AuditReport]) -> None:
    assert summary_line(sample_reports["robust"]) == (
        "run-length-encode: NO HOLES - holes: none; 5 blocked, 0 not applicable, 0 errors"
    )
    assert summary_line(sample_reports["hardcodable"]).startswith(
        "sensor-means: HOLES FOUND - holes: hardcode-visible-expected (high), "
        "conftest-force-pass (critical);"
    )


def test_reports_for_stopped_audits(make_task: TaskFactory) -> None:
    broken = run_audit(load_task(make_task(name="b", solution_command="echo nope; exit 4")))
    text = render_markdown(broken)
    assert "**Verdict: BROKEN REFERENCE**" in text
    assert "-> exit 4" in text
    assert "nope" in text
    assert "does not pass" in summary_line(broken)
    assert to_dict(broken)["baselines"]["empty"] is None

    lenient = run_audit(load_task(make_task(name="l", grader_command="true")))
    text = render_markdown(lenient)
    assert "**Verdict: ACCEPTS NO WORK**" in text
    assert "did nothing" in text
    assert "untouched starting workspace" in summary_line(lenient)


def test_join_collapses_blank_lines_outside_code_only() -> None:
    assert _join(["a", "", "", "```", "x", "", "", "```", "", ""]) == "a\n\n```\nx\n\n\n```\n"
