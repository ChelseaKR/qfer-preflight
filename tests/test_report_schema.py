"""The published JSON schema and the reports it claims to describe.

`docs/schemas/report-v1.schema.json` is the contract for `--format json`.
These tests keep the two sides from drifting apart in either direction: every
shape of report the engine can produce must validate against the schema, and
the schema must not grow constraints the real reports violate. Both directions
are covered by validating real output, never synthetic dictionaries.

The cases below are chosen to hit every conditional part of the model: a clean
file (unevaluated rules, no findings), a dirty file, a header mismatch (empty
findings with errors present), merges, advisories, and each profile's shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from qfer_preflight.engine import validate_bytes, validate_path
from qfer_preflight.model import REPORT_SCHEMA_VERSION, Report
from qfer_preflight.profiles import PROFILES, get_profile
from qfer_preflight.report import to_json

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_V1 = Path(__file__).resolve().parents[1] / "docs" / "schemas" / "report-v1.schema.json"

_validator = jsonschema.Draft202012Validator(json.loads(SCHEMA_V1.read_text(encoding="utf-8")))


def _assert_valid(report: Report) -> None:
    payload = report.to_dict()
    assert payload["schema_version"] == REPORT_SCHEMA_VERSION
    errors = sorted(_validator.iter_errors(payload), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)
    # The rendered JSON is the artifact callers actually receive.
    _validator.validate(json.loads(to_json(report)))


def test_clean_files_validate_for_every_profile() -> None:
    fixtures = {
        "CEC-1306A-S1": "1306a_s1_clean.csv",
        "CEC-1306B": "1306b_clean.csv",
        "CEC-1308B-S1": "1308b_s1_clean.csv",
        "CEC-1308C": "1308c_clean.csv",
    }
    for profile_id, fixture in fixtures.items():
        report = validate_path(str(FIXTURES / fixture), get_profile(profile_id))
        assert report.status.value == "unvalidated"
        _assert_valid(report)


def test_a_schedule_2_report_validates() -> None:
    """Schedule 2 has no dedicated fixture; its shape differs from the rest.

    It carries a QuarterNumber column instead of Month, no numeric-footnote
    columns, and therefore no numeric hygiene rules. The schema must hold for
    that shape too.
    """
    header = ",".join(get_profile("CEC-1306A-S2").header)
    body = "123,2025,2,Residential Rate A,Standard residential service"
    payload = f"{header}\r\n{body}\r\n".encode()
    report = validate_bytes(payload, get_profile("CEC-1306A-S2"), "s2.csv")
    assert report.error_count == 0
    _assert_valid(report)


def test_a_dirty_file_with_merged_findings_validates() -> None:
    """Two rows wrong in the same way produce one merged finding line."""
    header = ",".join(PROFILES["CEC-1306A-S1"].header)
    row = "123,2025,3,007,D,RESIDENTIAL_OTHER,925190,10,1000.50,25"
    payload = f"{header}\r\n{row}\r\n{row}\r\n".encode()
    report = validate_bytes(payload, PROFILES["CEC-1306A-S1"], "dirty.csv")

    assert report.status.value == "fail"
    merged = [f for f in report.findings if f.occurrences > 1]
    assert merged, "the fixture stopped producing merged findings"
    assert any(f.occurrences == 2 for f in merged)
    _assert_valid(report)


def test_reports_with_advisories_validate() -> None:
    header = ",".join(PROFILES["CEC-1306A-S1"].header)
    row = "123,2025,3,14,B,RESIDENTIAL_OTHER,925190,10,1000.50,25"
    bom_and_rows = f"\ufeff{header}\r\n{row}\r\n".encode()
    report = validate_bytes(bom_and_rows, PROFILES["CEC-1306A-S1"], "bom.csv")

    assert report.advisories, "the fixture stopped raising an advisory"
    _assert_valid(report)


def test_structurally_broken_files_still_validate() -> None:
    for name in ("empty.csv", "wrong_header.csv"):
        report = validate_path(str(FIXTURES / name), PROFILES["CEC-1306A-S1"])
        assert report.status.value == "fail"
        _assert_valid(report)


def test_unreadable_bytes_produce_a_validating_report() -> None:
    report = validate_bytes(
        b"\xff\xfe\x00\x00not utf-8 at all \xc3\x28",
        PROFILES["CEC-1306A-S1"],
        "binary.csv",
    )
    assert report.status.value == "fail"
    _assert_valid(report)


def test_schema_file_declares_version_one() -> None:
    schema = json.loads(SCHEMA_V1.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"] == {"const": 1}
    assert SCHEMA_V1.name == f"report-v{REPORT_SCHEMA_VERSION}.schema.json"
