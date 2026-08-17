"""End to end exercise of `--strict`.

`--strict` is the switch that turns "some rules were never applied" into a
non-zero exit, so a caller can wire this tool into a gate that refuses to treat
a partially validated filing as an acceptable one. Because the whole point of
the flag is the number the shell sees, most of these tests run the real command
line entry point in a subprocess and read the process exit status, rather than
calling `main()` in process.

The contract under test:

  * a file with no errors but with unevaluated rules exits 0 normally and 1
    under `--strict`;
  * `--strict` changes the exit code and nothing else, so the report body is
    byte identical either way;
  * `--strict` never downgrades a failure and never masks a usage error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from qfer_preflight.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, _cmd_check, build_parser
from qfer_preflight.model import Report, Status

FIXTURES = Path(__file__).parent / "fixtures"

# Every clean fixture, with the profile it belongs to. Each of these files has
# no findings at all, so the only thing keeping it away from `pass` is the set
# of rules that are registered but not implemented.
CLEAN_FIXTURES = [
    ("1306a_s1_clean.csv", "CEC-1306A-S1"),
    ("1306b_clean.csv", "CEC-1306B"),
    ("1308b_s1_clean.csv", "CEC-1308B-S1"),
    ("1308c_clean.csv", "CEC-1308C"),
]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the installed CLI the way a shell would."""
    return subprocess.run(
        [sys.executable, "-m", "qfer_preflight", *args],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# The exit code, through the real entry point
# ---------------------------------------------------------------------------


def test_clean_file_exits_zero_without_strict_and_one_with_it() -> None:
    args = ["check", str(FIXTURES / "1306a_s1_clean.csv"), "--profile", "CEC-1306A-S1"]

    lenient = _run(*args)
    strict = _run(*args, "--strict")

    assert lenient.returncode == EXIT_OK, lenient.stderr
    assert strict.returncode == EXIT_FINDINGS, strict.stderr
    assert "UNVALIDATED" in strict.stdout


@pytest.mark.parametrize("fixture,profile_id", CLEAN_FIXTURES)
def test_strict_fails_every_clean_fixture_because_rules_remain_unapplied(
    fixture: str, profile_id: str
) -> None:
    """No profile can reach a clean bill of health, so none may pass --strict."""
    args = ["check", str(FIXTURES / fixture), "--profile", profile_id]

    assert _run(*args).returncode == EXIT_OK
    assert _run(*args, "--strict").returncode == EXIT_FINDINGS


def test_strict_changes_the_exit_code_and_nothing_else() -> None:
    """The flag is a gate, not a different report."""
    args = ["check", str(FIXTURES / "1306a_s1_clean.csv"), "--profile", "CEC-1306A-S1"]

    lenient = _run(*args)
    strict = _run(*args, "--strict")

    assert lenient.stdout == strict.stdout
    assert lenient.stderr == strict.stderr == ""
    assert lenient.returncode != strict.returncode


def test_strict_does_not_downgrade_a_failing_file() -> None:
    args = ["check", str(FIXTURES / "1306a_s1_dirty.csv"), "--profile", "CEC-1306A-S1"]

    assert _run(*args).returncode == EXIT_FINDINGS
    assert _run(*args, "--strict").returncode == EXIT_FINDINGS


def test_strict_reports_a_structurally_broken_file_as_a_failure() -> None:
    """An unreadable file is already a failure; --strict must not soften it."""
    for fixture in ("empty.csv", "wrong_header.csv"):
        args = ["check", str(FIXTURES / fixture), "--profile", "CEC-1306A-S1"]
        assert _run(*args, "--strict").returncode == EXIT_FINDINGS


def test_strict_does_not_mask_a_usage_error() -> None:
    """A bad invocation stays exit 2, so callers can tell it from a finding."""
    unknown_profile = _run(
        "check", str(FIXTURES / "1306a_s1_clean.csv"), "--profile", "NOPE", "--strict"
    )
    assert unknown_profile.returncode == EXIT_USAGE
    assert "unknown profile" in unknown_profile.stderr

    missing_file = _run("check", "/nonexistent/nope.csv", "--profile", "CEC-1306A-S1", "--strict")
    assert missing_file.returncode == EXIT_USAGE
    assert "could not read" in missing_file.stderr


def test_strict_json_output_still_parses_and_names_what_was_skipped() -> None:
    result = _run(
        "check",
        str(FIXTURES / "1306a_s1_clean.csv"),
        "--profile",
        "CEC-1306A-S1",
        "--format",
        "json",
        "--strict",
    )
    assert result.returncode == EXIT_FINDINGS
    payload = json.loads(result.stdout)
    assert payload["status"] == "unvalidated"
    skipped = {item["rule_id"] for item in payload["rules_not_evaluated"]}
    assert {"QP005", "QP018", "QP032"} <= skipped
    for item in payload["rules_not_evaluated"]:
        assert item["reason"].strip()


# ---------------------------------------------------------------------------
# The flag itself
# ---------------------------------------------------------------------------


def test_strict_defaults_to_off() -> None:
    args = build_parser().parse_args(["check", "x.csv", "--profile", "CEC-1306A-S1"])
    assert args.strict is False


def test_strict_is_documented_in_the_help_text() -> None:
    # argparse wraps its help, so compare on collapsed whitespace.
    help_text = " ".join(_run("check", "--help").stdout.split())
    assert "--strict" in help_text
    assert "also exit non-zero when any rule could not be evaluated" in help_text


def test_strict_returns_zero_for_a_report_with_nothing_left_unevaluated(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one case real data cannot reach.

    Every profile registers at least one rule that is published but not
    mechanically checkable, so no real filing ever reaches `pass`. This test
    substitutes a report that did, to prove `--strict` gates on unevaluated
    rules rather than simply always failing.
    """
    complete = Report(
        tool="qfer-preflight",
        tool_version="0.0.0",
        profile_id="CEC-1306A-S1",
        profile_title="t",
        input_name="x.csv",
        input_sha256="0" * 64,
        rules_evaluated=["QP001"],
        rules_not_evaluated=[],
    )
    assert complete.status is Status.PASS

    monkeypatch.setattr("qfer_preflight.cli.validate_path", lambda *_: complete)
    args = argparse.Namespace(profile="CEC-1306A-S1", path="x.csv", format="text", strict=True)
    assert _cmd_check(args) == EXIT_OK
    assert "PASS" in capsys.readouterr().out
