"""Batch mode: several inputs, one run, no aggregation of findings.

The batch envelope is an outcome list, not a super-report. Each entry embeds
a complete single-report document, and the tests below hold the batch to two
promises:

  * Parity. A file's embedded report is byte-identical, as rendered JSON, to
    what validating that file alone produces. Batch mode changes nothing
    about how any single document is judged.
  * No silence. An input that cannot be processed appears with its problem
    stated; nothing is dropped because the rest of the batch succeeded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from qfer_preflight.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main
from qfer_preflight.model import BATCH_SCHEMA_VERSION, BatchEntry, Report
from qfer_preflight.report import batch_to_json

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = json.loads(
    (ROOT / "docs" / "schemas" / "report-v1.schema.json").read_text(encoding="utf-8")
)
BATCH_SCHEMA_PATH = ROOT / "docs" / "schemas" / "report-batch-v1.schema.json"
_batch_validator = jsonschema.Draft202012Validator(
    json.loads(BATCH_SCHEMA_PATH.read_text(encoding="utf-8"))
)


def _run_json(argv: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    code = main(argv)
    assert code in (EXIT_OK, EXIT_FINDINGS, EXIT_USAGE)
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    return payload


def _single_report(path: Path, profile_args: list[str]) -> str:
    from qfer_preflight.engine import validate_path
    from qfer_preflight.profiles import get_profile
    from qfer_preflight.report import to_json

    profile = get_profile(profile_args[-1])
    report = validate_path(str(path), profile)
    return to_json(report)


def test_batch_envelope_is_valid_against_its_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _run_json(
        [
            "check",
            str(FIXTURES / "1306a_s1_clean.csv"),
            str(FIXTURES / "1306b_clean.csv"),
            "--format",
            "json",
        ],
        capsys,
    )
    errors = sorted(_batch_validator.iter_errors(payload), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


def test_every_embedded_report_matches_its_single_run_byte_for_byte(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = FIXTURES / "1306a_s1_clean.csv"
    dirty = FIXTURES / "1306a_s1_dirty.csv"

    payload = _run_json(
        ["check", str(clean), str(dirty), "--profile", "CEC-1306A-S1", "--format", "json"],
        capsys,
    )
    results = {entry["input_name"]: entry for entry in payload["results"]}  # type: ignore[index]

    for path in (clean, dirty):
        embedded = json.dumps(results[str(path)]["report"], indent=2, sort_keys=True) + "\n"  # type: ignore[index]
        assert embedded == _single_report(path, ["--profile", "CEC-1306A-S1"])
        jsonschema.validate(results[str(path)]["report"], REPORT_SCHEMA)  # type: ignore[index]


def test_unprocessable_inputs_are_listed_never_dropped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    binary = tmp_path / "binary.csv"
    binary.write_bytes(b"\xff\xfe\x00\x00not utf-8 \xc3\x28")
    wrong = tmp_path / "wrong.csv"
    wrong.write_bytes(b"CompanyNumber,Year\r\n123,2025\r\n")

    code = main(["check", str(FIXTURES / "1306a_s1_clean.csv"), str(binary), str(wrong)])
    out = capsys.readouterr().out
    # The clean file validated with no findings; the two refusals are usage
    # problems, and the aggregate exit code reports them once nothing failed.
    assert code == EXIT_USAGE

    # The text summary names every input's verdict, including the refusals.
    for name in ("binary.csv", "wrong.csv", "NOT VALIDATED"):
        assert name in out


def test_exit_code_findings_outrank_usage_problems(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dirty = FIXTURES / "1306a_s1_dirty.csv"
    missing = tmp_path / "gone.csv"

    code = main(["check", str(dirty), str(missing), "--profile", "CEC-1306A-S1"])
    capsys.readouterr()
    assert code == EXIT_FINDINGS


def test_usage_only_batch_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["check", "/nonexistent/a.csv", "/nonexistent/b.csv"])
    capsys.readouterr()
    assert code == EXIT_USAGE


def test_directory_input_expands_in_name_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("c_second.csv", "a_first.csv", "b_third.csv"):
        (tmp_path / name).write_bytes((FIXTURES / "1306a_s1_clean.csv").read_bytes())

    payload = _run_json(["check", str(tmp_path), "--format", "json"], capsys)
    names = [entry["input_name"] for entry in payload["results"]]  # type: ignore[index]
    assert names == [str(tmp_path / n) for n in ("a_first.csv", "b_third.csv", "c_second.csv")]


def test_empty_directory_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check", str(tmp_path)]) == EXIT_USAGE
    assert "no files found" in capsys.readouterr().err


def test_strict_propagates_through_the_batch(capsys: pytest.CaptureFixture[str]) -> None:
    args = [
        "check",
        str(FIXTURES / "1306a_s1_clean.csv"),
        str(FIXTURES / "1306b_clean.csv"),
    ]
    assert main(args) == EXIT_OK
    capsys.readouterr()
    assert main([*args, "--strict"]) == EXIT_FINDINGS
    capsys.readouterr()


def test_a_single_file_still_produces_the_published_single_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One plain path keeps the v1 single-report output, not an envelope."""
    out = _run_json(
        [
            "check",
            str(FIXTURES / "1306a_s1_clean.csv"),
            "--profile",
            "CEC-1306A-S1",
            "--format",
            "json",
        ],
        capsys,
    )
    assert out["tool"] == "qfer-preflight"
    assert out["profile"]["id"] == "CEC-1306A-S1"  # type: ignore[index]
    assert "kind" not in out and "results" not in out


def test_batch_entry_requires_exactly_one_of_report_or_problem() -> None:
    report = Report(
        tool="t",
        tool_version="0",
        profile_id="X",
        profile_title="X",
        input_name="x",
        input_sha256="h",
    )
    with pytest.raises(ValueError):
        BatchEntry(input_name="x")  # type: ignore[call-arg]

    entry = BatchEntry(input_name="x", report=report)
    assert entry.to_dict()["outcome"] == "validated"
    problem = BatchEntry(input_name="y", problem="why")
    assert problem.to_dict()["outcome"] == "not-validated"


def test_batch_json_renders_from_entries_directly() -> None:
    from qfer_preflight.model import BatchEntry

    payload = json.loads(batch_to_json([BatchEntry(input_name="x", problem="p")], "t", "0"))
    assert payload["schema_version"] == BATCH_SCHEMA_VERSION
    assert payload["kind"] == "qfer-preflight/batch"
