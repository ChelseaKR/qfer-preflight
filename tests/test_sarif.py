"""The SARIF rendering stays derived from, and faithful to, the native report.

SARIF exists so the same findings can appear in surfaces that speak it. The
danger peculiar to a second rendering is drift: a document that grows its own
opinions about severity, drops the unevaluated rules, or dresses an advisory
up as a cited rule. These tests hold the rendering against the native report
it was derived from.

"Drops the unevaluated rules" needed a second reading. This file used to test
that they survived into `run.properties.rulesNotEvaluated` and call that
fidelity, but `properties` is an extension bag that no SARIF consumer reads,
so surviving into it is indistinguishable from being dropped for every reader
the rendering exists to serve. The assertions below hold the unevaluated rules
to `invocation.toolExecutionNotifications`, which is the standard's own place
for a condition that arose during a run and is not a result.

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
from qfer_preflight.model import Report, Status
from qfer_preflight.profiles import PROFILES, get_profile
from qfer_preflight.report import report_to_sarif, report_to_sarif_dict, to_text

FIXTURES = Path(__file__).parent / "fixtures"

_SARIF_VERSION = "2.1.0"
_SCHEMA_SUFFIX = "sarif-schema-2.1.0.json"

_UNEVALUATED_ID = "qfer/rule-not-evaluated"
_UNVALIDATED_ID = "qfer/not-reported-as-clean"


def _notifications(run: dict[str, Any]) -> list[dict[str, Any]]:
    return list(run["invocations"][0].get("toolExecutionNotifications", []))


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
    # And, because properties alone reach nobody, the verdict is also stated
    # where a consumer looks. An empty `results` array beside
    # `executionSuccessful: true` is what a false clean looks like in SARIF.
    assert any(n["descriptor"]["id"] == _UNVALIDATED_ID for n in _notifications(run))


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
        # Same exclusion as the rule test above. `bool` is a subclass of `int`,
        # so `isinstance(True, int)` holds and `rules[True]` silently resolves
        # to `rules[1]`: a wrong rule, resolved without complaint. The two
        # tests must agree on what the invariant is.
        assert isinstance(index, int) and not isinstance(index, bool), (
            f"ruleIndex for {result['ruleId']} is {type(index).__name__}, "
            "and SARIF 2.1.0 types it as an integer"
        )
        assert 0 <= index < len(rules), f"ruleIndex {index} is outside rules[]"
        assert rules[index]["id"] == result["ruleId"]


def test_every_unevaluated_rule_reaches_a_surface_a_consumer_reads() -> None:
    """An unevaluated rule must not be invisible to the reader SARIF is for.

    ADR 0001: a spotless filing reports `unvalidated`, because every profile
    registers rules that cannot be evaluated from published text. The text
    rendering prints that in capitals. This rendering carried it only in
    `run.properties`, an extension bag no SARIF consumer reads, so the same
    run reached a machine as an empty `results` array next to
    `executionSuccessful: true`. That is a false clean, which ADR 0001 names
    as the most dangerous failure a validator has.

    The parity asserted here is exact in both directions: every rule the
    native report says was never applied has a notification, and every
    notification names a rule the native report says was never applied. A
    subset check in either direction would let the two lists drift.
    """
    profile = get_profile("CEC-1306A-S1")
    report = validate_bytes(
        (FIXTURES / "1306a_s1_clean.csv").read_bytes(),
        profile,
        "1306a_s1_clean.csv",
    )
    assert report.status is Status.UNVALIDATED
    assert not report.checked_findings(), "the clean fixture must produce no findings"
    assert report.rules_not_evaluated, "the clean fixture must leave rules unevaluated"

    run = report_to_sarif_dict(report)["runs"][0]
    assert run["results"] == []

    notified = {
        n["properties"]["ruleId"]
        for n in _notifications(run)
        if n["descriptor"]["id"] == _UNEVALUATED_ID
    }
    assert notified == {item.rule_id for item in report.rules_not_evaluated}

    reasons = {item.rule_id: item.reason for item in report.rules_not_evaluated}
    for notification in _notifications(run):
        if notification["descriptor"]["id"] != _UNEVALUATED_ID:
            continue
        rule_id = notification["properties"]["ruleId"]
        text = notification["message"]["text"]
        # The reason travels with the rule. A notification saying only that
        # something went unevaluated, without saying what or why, is the same
        # silence in a louder font.
        assert reasons[rule_id] in text
        assert "did not pass" in text
        # "none" is the level SARIF consumers use to mean "do not show this".
        assert notification["level"] in {"note", "warning", "error"}


def test_a_notification_descriptor_index_resolves_to_the_descriptor_it_names() -> None:
    """The same round trip `ruleIndex` is held to, for notifications.

    `notification.descriptor` is a reportingDescriptorReference: its `index`
    is a position in `tool.driver.notifications`. A type check alone would
    accept an integer pointing at the wrong entry, which is the likelier
    future regression, so this indexes the array and checks it lands on the
    descriptor the notification names.
    """
    profile = get_profile("CEC-1306A-S1")
    report = validate_bytes(
        (FIXTURES / "1306a_s1_clean.csv").read_bytes(),
        profile,
        "1306a_s1_clean.csv",
    )
    run = report_to_sarif_dict(report)["runs"][0]
    descriptors = run["tool"]["driver"]["notifications"]
    notifications = _notifications(run)
    assert notifications, "the clean fixture must raise notifications to index"

    for notification in notifications:
        reference = notification["descriptor"]
        index = reference["index"]
        # `bool` is a subclass of `int`, so `descriptors[True]` silently
        # resolves to `descriptors[1]`: a wrong descriptor, resolved without
        # complaint. Same exclusion as the ruleIndex tests above.
        assert isinstance(index, int) and not isinstance(index, bool), (
            f"descriptor index for {reference['id']} is {type(index).__name__}"
        )
        assert 0 <= index < len(descriptors), f"index {index} is outside notifications[]"
        assert descriptors[index]["id"] == reference["id"], (
            f"index {index} resolves to {descriptors[index]['id']!r}, "
            f"but the notification names {reference['id']!r}"
        )

    # Catalogued once each, and only what was actually emitted. A descriptor
    # for something that did not happen is a claim about the run.
    ids = [descriptor["id"] for descriptor in descriptors]
    assert len(ids) == len(set(ids))
    assert set(ids) == {n["descriptor"]["id"] for n in notifications}


def test_the_verdict_sentence_is_identical_in_the_text_and_sarif_renderings() -> None:
    """One sentence, not two that can drift apart.

    Two renderings that each phrase the verdict for themselves is how one of
    them ends up phrasing it more softly than the other, and the softer one is
    the one a machine reads.
    """
    profile = get_profile("CEC-1306A-S1")
    report = validate_bytes(
        (FIXTURES / "1306a_s1_clean.csv").read_bytes(),
        profile,
        "1306a_s1_clean.csv",
    )
    text = to_text(report)
    run = report_to_sarif_dict(report)["runs"][0]
    verdicts = [n for n in _notifications(run) if n["descriptor"]["id"] == _UNVALIDATED_ID]
    assert len(verdicts) == 1
    sentence = verdicts[0]["message"]["text"]
    assert "NOT reported as clean" in sentence
    assert sentence in text
    assert verdicts[0]["properties"]["status"] == report.status.value


def test_a_file_that_could_not_be_read_says_so_about_every_other_rule() -> None:
    """The blocked case, where silence would be most costly.

    Undecodable bytes leave one QP001 result and every other rule unapplied.
    A consumer that read only `results` would see a single error and take the
    rest of the filing to have passed.
    """
    profile = get_profile("CEC-1306A-S1")
    body = ",".join(profile.header).encode("utf-8") + b"\r\n123,2025,\xff,14\r\n"
    report = validate_bytes(body, profile, "undecodable.csv")
    assert report.status is Status.FAIL
    blocked = {item.rule_id for item in report.rules_not_evaluated}
    assert len(blocked) > 1, "the undecodable fixture must block more than one rule"

    run = report_to_sarif_dict(report)["runs"][0]
    assert [r["ruleId"] for r in run["results"]] == ["QP001"]
    notified = {
        n["properties"]["ruleId"]
        for n in _notifications(run)
        if n["descriptor"]["id"] == _UNEVALUATED_ID
    }
    assert notified == blocked
    # FAIL is already loud in `results`, so the verdict notification is for
    # the case a consumer would otherwise read as clean, not this one.
    assert not [n for n in _notifications(run) if n["descriptor"]["id"] == _UNVALIDATED_ID]


def test_a_run_with_nothing_left_unsaid_carries_no_notifications() -> None:
    """No empty arrays standing in for a statement.

    A report with no unevaluated rules and no advisories has nothing for this
    channel to carry, and omits both keys rather than emitting empty arrays
    that a reader could take for a positive claim.
    """
    report = Report(
        tool="qfer-preflight",
        tool_version="0.0.0",
        profile_id="CEC-1306A-S1",
        profile_title="test",
        input_name="x.csv",
        input_sha256="0" * 64,
    )
    assert report.status is Status.PASS
    run = report_to_sarif_dict(report)["runs"][0]
    assert "notifications" not in run["tool"]["driver"]
    assert "toolExecutionNotifications" not in run["invocations"][0]
    assert run["invocations"][0]["executionSuccessful"] is True
