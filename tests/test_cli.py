"""CLI behaviour, exit codes and report rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qfer_preflight.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main
from qfer_preflight.model import (
    Citation,
    Finding,
    Report,
    Rule,
    Severity,
    Status,
)
from qfer_preflight.report import to_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_check_clean_file_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["check", str(FIXTURES / "1306a_s1_clean.csv"), "--profile", "CEC-1306A-S1"])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "UNVALIDATED" in out
    assert "NOT reported as clean" in out


def test_check_dirty_file_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["check", str(FIXTURES / "1306a_s1_dirty.csv"), "--profile", "CEC-1306A-S1"])
    assert code == EXIT_FINDINGS
    assert "ERROR" in capsys.readouterr().out


def test_empty_file_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["check", str(FIXTURES / "empty.csv"), "--profile", "CEC-1306A-S1"])
    capsys.readouterr()
    assert code == EXIT_FINDINGS


def test_strict_turns_unvalidated_into_a_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = ["check", str(FIXTURES / "1306a_s1_clean.csv"), "--profile", "CEC-1306A-S1"]
    assert main(args) == EXIT_OK
    capsys.readouterr()
    assert main([*args, "--strict"]) == EXIT_FINDINGS
    capsys.readouterr()


def test_json_output_is_valid_json(capsys: pytest.CaptureFixture[str]) -> None:
    main(
        [
            "check",
            str(FIXTURES / "1306a_s1_clean.csv"),
            "--profile",
            "CEC-1306A-S1",
            "--format",
            "json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "unvalidated"
    assert payload["profile"]["id"] == "CEC-1306A-S1"
    assert payload["input"]["sha256"]
    assert payload["rules_not_evaluated"]


def test_unknown_profile_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["check", str(FIXTURES / "empty.csv"), "--profile", "NOPE"])
    assert code == EXIT_USAGE
    assert "unknown profile" in capsys.readouterr().err


def test_missing_file_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["check", "/nonexistent/nope.csv", "--profile", "CEC-1306A-S1"])
    assert code == EXIT_USAGE
    assert "could not read" in capsys.readouterr().err


def test_rules_command_lists_citations(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rules"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "QP001" in out
    assert "energy.ca.gov" in out
    assert "NOT IMPLEMENTED" in out


def test_rules_command_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rules", "--format", "json", "--profile", "CEC-1308C"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert all("citation" in rule for rule in payload)


def test_rules_command_rejects_bad_profile(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["rules", "--profile", "NOPE"]) == EXIT_USAGE
    capsys.readouterr()


def test_profiles_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["profiles"]) == EXIT_OK
    out = capsys.readouterr().out
    for pid in ("CEC-1306A-S1", "CEC-1306B", "CEC-1308B-S1", "CEC-1308C"):
        assert pid in out
    # The published header irregularities must be visible, not silently fixed.
    assert "RetailRatClass" in out
    assert "NumberofCustomers" in out


def test_text_report_renders_findings() -> None:
    report = Report(
        tool="qfer-preflight",
        tool_version="0.0.0",
        profile_id="X",
        profile_title="X",
        input_name="x.csv",
        input_sha256="deadbeef",
    )
    report.findings.append(Finding("QP010", Severity.ERROR, "bad year", row=2, column="Year"))
    report.findings.append(Finding("QP030", Severity.WARNING, "spans quarters"))
    text = to_text(report)
    assert "row 2, Year" in text
    assert "[ERROR] QP010" in text
    assert "[WARN] QP030" in text


def test_text_report_handles_no_findings() -> None:
    report = Report(
        tool="t",
        tool_version="0",
        profile_id="X",
        profile_title="X",
        input_name="x",
        input_sha256="h",
    )
    assert "Findings: none" in to_text(report)
    assert report.status is Status.PASS


# ---------------------------------------------------------------------------
# Model guardrails
# ---------------------------------------------------------------------------


def _citation() -> Citation:
    return Citation(source="s", url="https://example.invalid", locator="l")


def test_citation_rejects_empty_fields() -> None:
    for kwargs in (
        {"source": "", "url": "u", "locator": "l"},
        {"source": "s", "url": "", "locator": "l"},
        {"source": "s", "url": "u", "locator": ""},
    ):
        with pytest.raises(ValueError):
            Citation(**kwargs)  # type: ignore[arg-type]


def test_rule_requires_a_reason_when_unimplemented() -> None:
    with pytest.raises(ValueError):
        Rule(
            id="QP900",
            title="t",
            severity=Severity.ERROR,
            citation=_citation(),
            implemented=False,
        )


def test_implemented_rule_may_not_carry_an_unimplemented_reason() -> None:
    with pytest.raises(ValueError):
        Rule(
            id="QP901",
            title="t",
            severity=Severity.ERROR,
            citation=_citation(),
            unimplemented_reason="because",
        )


def test_implemented_rule_may_not_have_unvalidated_severity() -> None:
    with pytest.raises(ValueError):
        Rule(
            id="QP902",
            title="t",
            severity=Severity.UNVALIDATED,
            citation=_citation(),
        )


def test_rule_requires_id_and_title() -> None:
    with pytest.raises(ValueError):
        Rule(id="", title="t", severity=Severity.ERROR, citation=_citation())
    with pytest.raises(ValueError):
        Rule(id="QP903", title=" ", severity=Severity.ERROR, citation=_citation())


def test_severity_and_status_stringify() -> None:
    assert str(Severity.ERROR) == "error"
    assert str(Status.PASS) == "pass"


def test_citation_render_includes_authority() -> None:
    cited = Citation(
        source="doc", url="https://example.invalid", locator="p1", authority="Title 20"
    )
    rendered = cited.render()
    assert "Title 20" in rendered
    assert "doc" in rendered
