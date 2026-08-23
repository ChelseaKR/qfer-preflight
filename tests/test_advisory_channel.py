"""The advisory channel, attacked on the assumption that it is the weak point.

Every finding this tool reports carries a rule identifier, and every rule
carries a citation to published text. An advisory carries neither. It is the
one thing in the output that asserts something on nobody's authority, which
makes it the obvious place for a check that could not survive as a rule to end
up: write a sentence, give it an `ADV-` code, and it reads to a filer exactly
like everything else in the report.

ADR 0004 answered that with structure rather than good intentions. This file
tries to get round the structure:

  * put an uncited assertion into the findings list;
  * construct an advisory that skips its own validation;
  * make a report that holds only advisories read as a clean one.

The tests are written as attacks, and each one is expected to fail to land.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from qfer_preflight import engine
from qfer_preflight.cli import EXIT_FINDINGS, EXIT_OK, main
from qfer_preflight.engine import validate_bytes
from qfer_preflight.model import (
    ADVISORY_CODES,
    Advisory,
    Finding,
    Report,
    Severity,
    Status,
)
from qfer_preflight.profiles import PROFILE_1306A_S1, PROFILES
from qfer_preflight.report import to_json, to_text
from qfer_preflight.rules import RULE_SPECS_BY_ID, specs_for

REPO = Path(__file__).resolve().parents[1]
HEADER = ",".join(PROFILE_1306A_S1.header)
GOOD_ROW = "101,2025,1,34,B,A1,925190,1200,4500000,675000.25"
BOM_FILE = b"\xef\xbb\xbf" + f"{HEADER}\n{GOOD_ROW}\n".encode()


def _check(body: str | bytes) -> Report:
    data = body.encode() if isinstance(body, str) else body
    return validate_bytes(data, PROFILE_1306A_S1, "input.csv")


def _advisory() -> Advisory:
    return Advisory(code="ADV-BOM", message="something, and no published rule covers it")


# ---------------------------------------------------------------------------
# Attack 1: get an uncited assertion into the findings list
# ---------------------------------------------------------------------------


def test_an_advisory_placed_in_the_findings_list_refuses_to_render() -> None:
    """The direct approach. Both renderings must refuse, not improvise."""
    report = Report(
        tool="t",
        tool_version="0",
        profile_id="X",
        profile_title="X",
        input_name="x",
        input_sha256="h",
    )
    report.findings.append(_advisory())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="Advisory in the findings list"):
        to_json(report)
    with pytest.raises(TypeError, match="Advisory in the findings list"):
        to_text(report)
    with pytest.raises(TypeError):
        _ = report.error_count


def test_a_finding_placed_in_the_advisory_list_refuses_to_render() -> None:
    """The same door, from the other side."""
    report = Report(
        tool="t",
        tool_version="0",
        profile_id="X",
        profile_title="X",
        input_name="x",
        input_sha256="h",
    )
    report.advisories.append(Finding("QP013", Severity.ERROR, "m"))  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="Finding in the advisory list"):
        to_json(report)


def test_a_finding_cannot_cite_a_rule_that_is_not_in_the_registry() -> None:
    collector = engine._Collector(specs_for(PROFILE_1306A_S1), PROFILE_1306A_S1)
    with pytest.raises(KeyError):
        collector.add("QP999", "invented")


def test_a_finding_cannot_cite_a_rule_the_report_says_it_never_applied() -> None:
    """QP005, QP018 and QP032 are registered precisely because nothing can test them.

    A finding attributed to one would be a report claiming a result from a
    check it also lists as unevaluated, on the same page.
    """
    collector = engine._Collector(specs_for(PROFILE_1306A_S1), PROFILE_1306A_S1)
    for rule_id in ("QP005", "QP018", "QP032"):
        with pytest.raises(ValueError, match="unimplemented"):
            collector.add(rule_id, "a totals row, probably")


def test_every_finding_in_every_report_traces_to_a_citation() -> None:
    """The property the findings list exists to keep."""
    bodies = [
        f"{HEADER}\n{GOOD_ROW}\n",
        f"{HEADER}\n101,2025,13,77,X,A1,12345,NULL,1,1\n",
        f"{HEADER}\n\n\n",
        "not a csv at all\n",
        "",
    ]
    for profile in PROFILES.values():
        for body in bodies:
            report = validate_bytes(body.encode(), profile, "x.csv")
            for finding in report.findings:
                spec = RULE_SPECS_BY_ID[finding.rule_id]
                citation = spec.bind(profile).citation
                assert citation.url.startswith("https://"), finding.rule_id
                assert citation.locator.strip()
                assert finding.rule_id in report.rules_evaluated


# ---------------------------------------------------------------------------
# Attack 2: construct an advisory that skips its own checks
# ---------------------------------------------------------------------------


def test_an_advisory_code_outside_the_registry_is_refused() -> None:
    """A new advisory has to be registered next to the others, not smuggled."""
    with pytest.raises(ValueError, match="not registered"):
        Advisory(code="ADV-COUNTY-LOOKS-ODD", message="no published rule covers it")


def test_an_advisory_code_that_looks_like_a_rule_is_refused() -> None:
    for code in ("QP099", "ADV", "adv-bom", ""):
        with pytest.raises(ValueError):
            Advisory(code=code, message="no published rule covers it")


def test_an_advisory_must_disclaim_published_cover_in_its_own_words() -> None:
    """The message is the only place a reader learns there is no citation."""
    with pytest.raises(ValueError, match="published record does not cover"):
        Advisory(code="ADV-BOM", message="This value is wrong. Fix it.")


def test_an_advisory_must_say_something() -> None:
    with pytest.raises(ValueError, match="must say what it noticed"):
        Advisory(code="ADV-BOM", message="   ")


def test_replacing_a_field_on_an_advisory_re_runs_its_checks() -> None:
    """`dataclasses.replace` is the ordinary way round a frozen object."""
    with pytest.raises(ValueError, match="not registered"):
        dataclasses.replace(_advisory(), code="ADV-INVENTED")
    with pytest.raises(ValueError, match="published record does not cover"):
        dataclasses.replace(_advisory(), message="this row is wrong")


def test_an_advisory_has_nowhere_to_put_a_severity_or_a_citation() -> None:
    """Not enforced by a check. Enforced by the fields not existing."""
    fields = {f.name for f in dataclasses.fields(Advisory)}
    assert fields == {"code", "message", "row", "column", "occurrences"}
    assert not hasattr(_advisory(), "severity")
    assert not hasattr(_advisory(), "citation")
    assert not hasattr(_advisory(), "rule_id")
    assert "severity" not in _advisory().to_dict()


def test_every_advisory_the_engine_can_raise_is_registered() -> None:
    """No code reaches a report without an entry in the table."""
    raised = set()
    for body in (
        BOM_FILE,
        f"{HEADER}\r{GOOD_ROW}\r".encode(),
        f"{HEADER}\n=1+1,2025,1,34,B,A1,925190,1200,4500000,1\n".encode(),
        f'{HEADER}\n101,2025,1,34,B,"A1\nA2",925190,1200,4500000,1\n'.encode(),
        f"{HEADER}\n{GOOD_ROW}\n{HEADER}\n".encode(),
    ):
        raised |= {a.code for a in _check(body).advisories}

    assert raised == set(ADVISORY_CODES), raised
    assert all(code.startswith("ADV-") for code in ADVISORY_CODES)


def test_every_registered_advisory_is_documented_in_the_readme() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    for code in ADVISORY_CODES:
        assert f"`{code}`" in readme, f"{code} is raised but never explained"


def test_every_advisory_raised_on_real_input_disclaims_published_cover() -> None:
    """The construction check, observed end to end rather than in isolation."""
    for body in (
        BOM_FILE,
        f"{HEADER}\r{GOOD_ROW}\r".encode(),
        f"{HEADER}\n{'=1,2025,1,34,B,A1,925190,1,1,1' * 1}\n".encode(),
        f'{HEADER}\n101,2025,1,34,B,"A1\nA2",925190,1200,4500000,1\n'.encode(),
        f"{HEADER}\n{GOOD_ROW}\n{HEADER}\n".encode(),
    ):
        for advisory in _check(body).advisories:
            assert "no published" in advisory.message.casefold(), advisory.code


def test_the_capped_tail_advisory_disclaims_cover_like_any_other() -> None:
    """The summary line the cap produces is an advisory too, and says so."""
    rows = "\n".join("123,2025,1,34,B,=1,925190,1,1,1" for _ in range(50))
    report = _check(f"{HEADER}\n{rows}\n")
    tail = next(a for a in report.advisories if a.occurrences == 50)

    assert "no published CEC document addresses any of them" in tail.message
    assert not hasattr(tail, "severity")
    assert tail.to_dict()["occurrences"] == 50
    assert json.loads(to_json(report))["counts"]["error"] == 0


def test_an_advisory_cannot_claim_fewer_than_one_occurrence() -> None:
    with pytest.raises(ValueError, match="occurrences"):
        Advisory(code="ADV-BOM", message="no published rule covers it", occurrences=0)


# ---------------------------------------------------------------------------
# Attack 3: make a report of advisories read as a clean one
# ---------------------------------------------------------------------------


def test_a_report_holding_only_advisories_is_never_a_pass() -> None:
    report = _check(BOM_FILE)

    assert report.findings == []
    assert report.advisories
    assert report.status is Status.UNVALIDATED


def test_an_advisory_alone_keeps_a_report_off_pass_even_with_nothing_unevaluated() -> None:
    """Constructed directly, because no real filing evaluates every rule."""
    report = Report(
        tool="t",
        tool_version="0",
        profile_id="X",
        profile_title="X",
        input_name="x",
        input_sha256="h",
        rules_evaluated=["QP001"],
        rules_not_evaluated=[],
    )
    without_advisory = report.status
    assert without_advisory is Status.PASS

    report.advisories.append(_advisory())
    with_advisory = report.status
    assert with_advisory is Status.UNVALIDATED


def test_the_text_of_an_advisory_only_report_never_reads_clean() -> None:
    text = to_text(_check(BOM_FILE))

    assert "status  : UNVALIDATED" in text
    assert "NOT reported as clean" in text
    assert "These are not CEC rules" in text
    assert "PASS" not in text


def test_the_json_of_an_advisory_only_report_never_reads_clean() -> None:
    payload = json.loads(to_json(_check(BOM_FILE)))

    assert payload["status"] == "unvalidated"
    assert payload["counts"]["advisory"] >= 1
    assert payload["counts"]["error"] == 0


def test_strict_fails_on_a_file_whose_only_complaint_is_an_advisory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate a caller wires into CI has to see the advisory."""
    path = tmp_path / "bom.csv"
    path.write_bytes(BOM_FILE)
    args = ["check", str(path), "--profile", "CEC-1306A-S1"]

    assert main(args) == EXIT_OK
    capsys.readouterr()
    assert main([*args, "--strict"]) == EXIT_FINDINGS
    assert "ADV-BOM" in capsys.readouterr().out


def test_an_advisory_is_rendered_in_its_own_block_never_as_a_finding() -> None:
    text = to_text(_check(BOM_FILE))
    findings_block, advisory_block = text.split("Advisories (")

    assert "ADV-BOM" not in findings_block
    assert "Findings: none" in findings_block
    assert "[ADVIS] ADV-BOM" in advisory_block
    for label in ("[ERROR]", "[WARN]", "[INFO]"):
        assert label not in advisory_block
