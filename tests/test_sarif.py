"""The SARIF rendering stays derived from, and faithful to, the native report.

SARIF exists so the same findings can appear in surfaces that speak it. The
danger peculiar to a second rendering is drift: a document that grows its own
opinions about severity, drops the unevaluated rules, or dresses an advisory
up as a cited rule. These tests hold the rendering against the native report
it was derived from.

No SARIF schema file is vendored here; the structural assertions below pin
the parts of the standard this tool relies on, and the fidelity assertions
pin everything this tool adds on top.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qfer_preflight.cli import EXIT_FINDINGS, EXIT_OK, main
from qfer_preflight.engine import validate_bytes
from qfer_preflight.profiles import PROFILES, get_profile
from qfer_preflight.report import report_to_sarif, report_to_sarif_dict

FIXTURES = Path(__file__).parent / "fixtures"

_SARIF_VERSION = "2.1.0"
_SCHEMA_SUFFIX = "sarif-schema-2.1.0.json"


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> Any:
    code = main(argv)
    assert code in (EXIT_OK, EXIT_FINDINGS)
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_clean_fixture_produces_a_sarif_log_with_no_results(
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = _run(
        [
            "check",
            str(FIXTURES / "1306a_s1_clean.csv"),
            "--profile",
            "CEC-1306A-S1",
            "--format",
            "sarif",
        ],
        capsys,
    )
    assert payload["version"] == _SARIF_VERSION
    assert payload["$schema"].endswith(_SCHEMA_SUFFIX)
    run = payload["runs"][0]
    assert run["tool"]["driver"]["name"] == "qfer-preflight"
    assert run["results"] == []
    # What SARIF cannot carry natively survives in properties.
    assert run["properties"]["status"] == "unvalidated"
    not_evaluated = run["properties"]["rulesNotEvaluated"]
    assert {entry["rule_id"] for entry in not_evaluated} >= {"QP005", "QP018", "QP032"}
    assert all(entry["reason"] for entry in not_evaluated)


def test_dirty_fixture_maps_severities_and_locations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    dirty = FIXTURES / "1306a_s1_dirty.csv"
    payload = _run(["check", str(dirty), "--profile", "CEC-1306A-S1", "--format", "sarif"], capsys)
    run = payload["runs"][0]

    results = [r for r in run["results"] if r["level"] != "none"]
    assert results, "the dirty fixture stopped producing findings"
    for result in results:
        assert result["level"] in {"error", "warning", "note"}
        rule = next(r for r in run["tool"]["driver"]["rules"] if r["id"] == result["ruleId"])
        assert rule["defaultConfiguration"]["level"] == result["level"]
        # Every cited rule carries the citation and quote it stands on.
        assert "energy.ca.gov" in rule["helpUri"]
        assert rule["fullDescription"]["text"]
        location = result["locations"][0]["physicalLocation"]
        # SARIF records the artifact as given: the basename the report saw.
        assert location["artifactLocation"]["uri"] == dirty.name
        assert location["region"]["startLine"] >= 2


def test_merged_findings_become_one_result_that_names_its_rows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    header = ",".join(PROFILES["CEC-1306A-S1"].header)
    row = "123,2025,3,007,D,RESIDENTIAL_OTHER,925190,10,1000.50,25"
    target = tmp_path / "merged.csv"
    target.write_text(f"{header}\r\n{row}\r\n{row}\r\n", encoding="utf-8")

    payload = _run(["check", str(target), "--format", "sarif"], capsys)
    run = payload["runs"][0]
    county_results = [
        r for r in run["results"] if r["ruleId"] == "QP013" and r["properties"].get("occurrences")
    ]
    assert len(county_results) == 1
    merged = county_results[0]
    assert merged["properties"]["occurrences"] == 2
    assert len(merged["properties"]["exampleRows"]) == 2
    assert "stands for 2 rows" in merged["message"]["text"]
    assert merged["locations"][0]["physicalLocation"]["region"]["endLine"] == 3


def test_advisories_stay_unseverityed_and_uncited_in_sarif(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    header = ",".join(PROFILES["CEC-1306A-S1"].header)
    row = "123,2025,3,14,B,RESIDENTIAL_OTHER,925190,10,1000.50,25"
    target = tmp_path / "bom.csv"
    target.write_text("\ufeff" + f"{header}\r\n{row}\r\n", encoding="utf-8")

    payload = _run(["check", str(target), "--format", "sarif"], capsys)
    run = payload["runs"][0]
    advisory_results = [r for r in run["results"] if r["level"] == "none"]
    assert advisory_results, "the fixture stopped raising an advisory"
    rules_by_id = {r["id"]: r for r in run["tool"]["driver"]["rules"]}
    for result in advisory_results:
        assert result["ruleId"].startswith("ADV-")
        rule = rules_by_id[result["ruleId"]]
        assert rule["properties"]["advisory"] is True
        assert "no published CEC document" in rule["fullDescription"]["text"]
        # An advisory must not borrow the credibility of a citation.
        assert "energy.ca.gov" not in json.dumps(rule)


def test_batch_mode_yields_one_run_per_input(capsys: pytest.CaptureFixture[str]) -> None:
    clean = FIXTURES / "1306a_s1_clean.csv"
    missing = "/nonexistent/nope.csv"
    code = main(["check", str(clean), missing, "--format", "sarif"])
    payload = json.loads(capsys.readouterr().out)

    # One clean file, one refusal: usage problems surface as exit 2 once no
    # filing failed, but every input still gets its run.
    assert code == 2
    assert len(payload["runs"]) == 2
    by_name = {run["properties"]["inputName"]: run for run in payload["runs"]}
    assert by_name[missing]["results"] == []
    assert "could not read" in by_name[missing]["properties"]["problem"]
    assert by_name[missing]["invocations"][0]["executionSuccessful"] is False


def test_sarif_rendering_is_deterministic(tmp_path: Path) -> None:
    profile = get_profile("CEC-1306A-S1")
    payload = (",".join(profile.header) + "\r\n123,2025,13,x\r\n").encode("utf-8")
    first = report_to_sarif(validate_bytes(payload, profile, "x.csv"))
    second = report_to_sarif(validate_bytes(payload, profile, "x.csv"))
    assert first == second


def test_rule_index_is_an_integer_that_resolves_to_the_named_rule() -> None:
    """`ruleIndex` must be the rule's position, not its name.

    SARIF 2.1.0 types `result.ruleIndex` as an integer: the zero-based index
    into `runs[].tool.driver.rules`. This rendering carried the rule's own
    identifier there instead, so a consumer resolving a result to its rule by
    index found a string where the standard promises a number, and the field
    duplicated `ruleId` rather than doing its job. Shipped in v0.2.0.

    The assertion that matters is the round trip: index into the rules array
    and land on the rule the result names. A type check alone would pass an
    integer that pointed at the wrong entry.
    """
    profile = get_profile("CEC-1306A-S1")
    report = validate_bytes(
        (FIXTURES / "1306a_s1_dirty.csv").read_bytes(),
        profile,
        "1306a_s1_dirty.csv",
    )
    run = report_to_sarif_dict(report)["runs"][0]
    rules = run["tool"]["driver"]["rules"]
    assert run["results"], "the dirty fixture must produce results to index"

    for result in run["results"]:
        index = result["ruleIndex"]
        assert isinstance(index, int) and not isinstance(index, bool), (
            f"ruleIndex for {result['ruleId']} is {type(index).__name__}, "
            "and SARIF 2.1.0 types it as an integer"
        )
        assert 0 <= index < len(rules), f"ruleIndex {index} is outside rules[]"
        assert rules[index]["id"] == result["ruleId"], (
            f"ruleIndex {index} resolves to {rules[index]['id']!r}, "
            f"but the result names {result['ruleId']!r}"
        )


def test_every_advisory_result_also_resolves_by_index() -> None:
    """Advisories share the rules array, so they share the invariant."""
    # A repeated header row is a QP007 error on CEC-1306B and CEC-1308C,
    # whose instructions publish the words "extra headers", and an advisory on
    # the other three, whose text does not. See ADR 0007. The advisory channel
    # is what this test needs, so it uses one of the latter.
    profile = get_profile("CEC-1306A-S1")
    header = ",".join(profile.header)
    body = f"{header}\r\n{header}\r\n".encode()
    report = validate_bytes(body, profile, "repeated_header.csv")
    run = report_to_sarif_dict(report)["runs"][0]
    rules = run["tool"]["driver"]["rules"]
    advisory_results = [r for r in run["results"] if r["ruleId"].startswith("ADV-")]
    assert advisory_results, "expected a repeated header to raise an advisory"

    for result in advisory_results:
        index = result["ruleIndex"]
        assert isinstance(index, int)
        assert rules[index]["id"] == result["ruleId"]
