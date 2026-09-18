"""QP018 against a list the caller holds, and every way that list is refused.

The Commission does not publish its "Valid NAICS codes" list and has said it
does not plan to (ADR 0009), so this tool ships none, fetches none, and reports
QP018 as not evaluated on every ordinary run. A filer with portal access holds
the data dictionary that carries it. `--naics-list` lets that filer supply it
for their own run.

Three properties are the whole of it and each has tests below.

1. **A run without the flag is unchanged, byte for byte.** The list is an
   addition to what the tool can be asked to do, not a change to what it does.
2. **A refused list is not a missing list.** Both leave QP018 unevaluated, and
   they say different things about why, because a filer who mistyped a path and
   a filer who passed no flag are in different situations.
3. **The report never claims the list is the Commission's, and never reprints
   it.** The provenance record says where the codes came from; the codes
   themselves stay in the caller's file.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from qfer_preflight import validate
from qfer_preflight.engine import validate_path
from qfer_preflight.model import Report, Status
from qfer_preflight.profiles import get_profile
from qfer_preflight.report import to_json, to_text
from qfer_preflight.supplied_codes import (
    CodeListRefused,
    NaicsListOffer,
    load_naics_list,
    offer_naics_list,
)

FIXTURES = Path(__file__).parent / "fixtures"
CLEAN = FIXTURES / "1306a_s1_clean.csv"
DIRTY = FIXTURES / "1306a_s1_dirty.csv"
PROFILE = get_profile("CEC-1306A-S1")
SCHEMA_V1 = Path(__file__).resolve().parents[1] / "docs" / "schemas" / "report-v1.schema.json"

# Every NAICS code the clean fixture uses. A list holding these is a list under
# which that filing has nothing wrong with it, which is the case a membership
# check is easiest to get wrong in: a rule that judged nothing looks exactly
# like a rule that judged everything and found nothing.
CLEAN_CODES = ("RE1100", "925190", "999999")


def write_list(tmp_path: Path, *codes: str, name: str = "codes.txt") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(codes) + "\n", encoding="utf-8")
    return path


def rule_reason(report: Report, rule_id: str) -> str | None:
    for item in report.rules_not_evaluated:
        if item.rule_id == rule_id:
            return item.reason
    return None


# --- the loader's refusals ------------------------------------------------------------


def test_a_well_formed_list_records_its_digest_and_counts(tmp_path: Path) -> None:
    path = write_list(tmp_path, "111111", "222222", "111111")
    supplied = load_naics_list(str(path))
    assert supplied.codes == frozenset({"111111", "222222"})
    assert supplied.lines == 3, "three lines were read, two of them distinct"
    assert supplied.path == str(path), "the path is recorded as given, not resolved"
    assert len(supplied.sha256) == 64
    assert supplied.sha256 == __import__("hashlib").sha256(path.read_bytes()).hexdigest()


def test_the_provenance_record_never_carries_the_codes(tmp_path: Path) -> None:
    """A report is a document a filer forwards.

    The Commission declined to publish this list. Reproducing it inside an
    artifact this tool writes, as a side effect of checking one column, would
    republish somebody else's withheld material.
    """
    path = write_list(tmp_path, *CLEAN_CODES)
    provenance = load_naics_list(str(path)).provenance()
    rendered = json.dumps(provenance)
    for code in CLEAN_CODES:
        assert code not in rendered
    assert provenance["codes"] == 3
    assert provenance["provenance"] == "caller_supplied"


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("empty.txt", b"", "holds no lines"),
        ("bom.txt", b"\xef\xbb\xbf111111\n", "byte order mark"),
        ("latin1.txt", b"1111\xff1\n", "not valid UTF-8"),
        ("blank_line.txt", b"111111\n\n222222\n", "exactly 6 characters"),
        ("short.txt", b"11111\n", "exactly 6 characters"),
        ("padded.txt", b"111111 \n", "exactly 6 characters"),
        ("header.txt", b"NAICSCode\n111111\n", "exactly 6 characters"),
        ("comment.txt", b"# codes\n111111\n", "exactly 6 characters"),
    ],
)
def test_a_list_that_is_not_a_code_list_is_refused(
    tmp_path: Path, name: str, content: bytes, expected: str
) -> None:
    """Fail closed, every time, and say which file and what about it.

    A code list read wrong is worse than no code list. A stray space on one line
    turns a perfectly valid code into one that matches nothing, and the QP018
    error that follows names a correct filing as wrong. The list is refused
    instead, which is the mistake a person can see and fix.
    """
    path = tmp_path / name
    path.write_bytes(content)
    with pytest.raises(CodeListRefused) as raised:
        load_naics_list(str(path))
    message = str(raised.value)
    assert expected in message
    assert str(path) in message
    assert "not checked" in message


def test_a_wholly_wrong_file_names_five_lines_rather_than_all_of_them(tmp_path: Path) -> None:
    """A refusal that reprints the file is not a refusal anybody reads.

    Pointed at a CSV by mistake, the loop would otherwise build one line of
    message per row of a large file. Five is enough to show the shape of what is
    wrong; the count is not claimed, because a truncated list presented as the
    whole of it is exactly the defect this project hunts.
    """
    path = tmp_path / "wrong.txt"
    path.write_text("\n".join(f"row {n}" for n in range(1, 40)) + "\n", encoding="utf-8")
    with pytest.raises(CodeListRefused) as raised:
        load_naics_list(str(path))
    message = str(raised.value)
    assert message.count("holds ") == 5
    assert "line 5 holds" in message
    assert "line 6 holds" not in message


def test_a_missing_file_is_refused_rather_than_read_as_an_empty_list(tmp_path: Path) -> None:
    """The one refusal that could plausibly have become a silent no-op.

    An unreadable path treated as "no codes" would refuse every code in the
    filing; treated as "no list" it would report QP018 unevaluated with the
    published-nowhere reason, which is a sentence about the Commission and not
    about the typo that actually happened.
    """
    offer = offer_naics_list(str(tmp_path / "nope.txt"))
    assert offer.accepted is None
    assert offer.refusal is not None
    assert "could not be read" in offer.refusal


def test_an_offer_is_accepted_or_refused_and_never_both_or_neither() -> None:
    """The three-state carrier cannot be built into a two-state one."""
    with pytest.raises(ValueError, match="either accepted or refused"):
        NaicsListOffer(accepted=None, refusal=None)


# --- a run with no list is the run this tool has always made --------------------------


def test_without_the_flag_the_report_is_byte_identical(tmp_path: Path) -> None:
    """The proof that this is an addition rather than a change.

    Compared as bytes, in both renderings, because the JSON is what a machine
    reads and the text is what a person reads and either could have grown a
    line that only shows up when a list is absent.
    """
    baseline = validate_path(str(DIRTY), PROFILE)
    with_none = validate_path(str(DIRTY), PROFILE, None, None)
    assert to_json(with_none) == to_json(baseline)
    assert to_text(with_none) == to_text(baseline)
    assert "code_lists" not in json.loads(to_json(with_none))


def test_without_the_flag_qp018_still_says_the_list_is_published_nowhere() -> None:
    report = validate_path(str(CLEAN), PROFILE)
    reason = rule_reason(report, "QP018")
    assert reason is not None
    assert "resolves to nothing public" in reason
    assert report.status is Status.UNVALIDATED


# --- a run with a list ----------------------------------------------------------------


def test_a_code_absent_from_the_list_is_a_qp018_error_naming_the_hash(tmp_path: Path) -> None:
    path = write_list(tmp_path, "111111", "222222")
    supplied = load_naics_list(str(path))
    report = validate_path(str(CLEAN), PROFILE, None, offer_naics_list(str(path)))
    findings = [f for f in report.findings if f.rule_id == "QP018"]
    assert findings, "the clean fixture's codes are not on this list"
    assert all(f.severity.value == "error" for f in findings)
    assert supplied.sha256 in findings[0].message
    assert str(path) in findings[0].message
    assert "QP018" not in {item.rule_id for item in report.rules_not_evaluated}
    assert "QP018" in report.rules_evaluated


def test_a_filing_whose_codes_are_all_on_the_list_raises_no_qp018_finding(
    tmp_path: Path,
) -> None:
    """And QP018 is reported as evaluated, not as silent.

    A rule that judged every row and found nothing and a rule that never ran
    produce the same empty findings list. Only the ledger tells them apart, so
    the ledger is what is asserted.
    """
    path = write_list(tmp_path, *CLEAN_CODES)
    report = validate_path(str(CLEAN), PROFILE, None, offer_naics_list(str(path)))
    assert [f for f in report.findings if f.rule_id == "QP018"] == []
    assert "QP018" in report.rules_evaluated
    entries = [e for e in report.evaluation if e.rule_id == "QP018"]
    assert len(entries) == 1
    assert entries[0].column == "NAICSCode"
    assert entries[0].judged == 3, "one verdict per data row in the fixture"
    assert entries[0].evaluated is True


def test_a_wrong_length_code_is_blocked_by_qp017_rather_than_failed_twice(
    tmp_path: Path,
) -> None:
    """Every code on an accepted list is six characters, so a five-character
    value is definitively absent from it. Reporting that under QP018 as well
    would tell a filer their code is off the list while QP017 is already telling
    them to replace it. The ledger says which rule stopped it, so the row is
    accounted for rather than quietly uncounted.
    """
    path = write_list(tmp_path, "111111")
    report = validate_path(str(DIRTY), PROFILE, None, offer_naics_list(str(path)))
    qp017 = [f for f in report.findings if f.rule_id == "QP017"]
    assert qp017, "the dirty fixture carries a five-character code"
    entry = next(e for e in report.evaluation if e.rule_id == "QP018")
    assert entry.blocked >= 1
    assert entry.blocked_by == "QP017"
    rows = {f.row for f in report.findings if f.rule_id == "QP018"}
    short_rows = {f.row for f in qp017}
    assert not (rows & short_rows), "no row carries both a length error and a membership one"


def test_qp017s_own_sentence_stops_claiming_qp018_was_not_evaluated(tmp_path: Path) -> None:
    """A sentence about another rule's outcome goes stale when that outcome varies.

    QP017's message ended "...is reported as not evaluated under QP018", which
    was true of every run until this one. Nothing but this test says so.
    """
    without = validate_path(str(DIRTY), PROFILE)
    said = next(f.message for f in without.findings if f.rule_id == "QP017")
    assert "reported as not evaluated under QP018" in said

    path = write_list(tmp_path, "111111")
    with_list = validate_path(str(DIRTY), PROFILE, None, offer_naics_list(str(path)))
    now = next(f.message for f in with_list.findings if f.rule_id == "QP017")
    assert "reported as not evaluated under QP018" not in now
    assert "supplied list" in now


def test_the_hint_names_a_transform_of_the_filings_own_value_never_a_list_member(
    tmp_path: Path,
) -> None:
    """The report may be forwarded, so the hint counts rather than quotes.

    A zero-padding hint names the filing's own value corrected, which is already
    in the report. A prefix hint names how many codes share four characters and
    stops there.
    """
    path = write_list(tmp_path, "221311", "221312", "221320")
    report = validate_path(str(CLEAN), PROFILE, None, offer_naics_list(str(path)))
    message = " ".join(f.message for f in report.findings if f.rule_id == "QP018")
    for code in ("221311", "221312", "221320"):
        assert code not in message, "a list member reached the report"


def test_the_prefix_hint_counts_the_near_codes_and_does_not_name_them(tmp_path: Path) -> None:
    """The other half of the hint, and the half that could have leaked codes.

    A value with no matching transform still deserves a pointer, and the only
    pointer available is "the list holds N codes beginning like yours". Naming
    them would put a slice of a withheld list into a document a filer forwards.
    """
    path = write_list(tmp_path, "925191", "925192", "RE1100", "999999")
    report = validate_path(str(CLEAN), PROFILE, None, offer_naics_list(str(path)))
    message = next(f.message for f in report.findings if f.rule_id == "QP018")
    assert "holds 2 codes beginning 9251" in message
    assert "does not republish" in message
    assert "925191" not in message
    assert "925192" not in message


def test_a_leading_zero_hint_is_offered_when_it_would_have_matched(tmp_path: Path) -> None:
    csv_path = tmp_path / "padded.csv"
    csv_path.write_text(
        CLEAN.read_text(encoding="utf-8").replace(",925190,", ",92519,"),
        encoding="utf-8",
    )
    path = write_list(tmp_path, "092519", "RE1100", "999999")
    report = validate_path(str(csv_path), PROFILE, None, offer_naics_list(str(path)))
    qp017 = [f for f in report.findings if f.rule_id == "QP017"]
    assert qp017, "a five-character value is a QP017 length error first"
    # And QP018 does not also fail it, which is the blocked case above. The
    # padding hint is reachable only for a six-character value, so it is
    # exercised by a value of the right length that is not on the list.
    path2 = write_list(tmp_path, "025190", name="codes2.txt")
    spaced = tmp_path / "spaced.csv"
    spaced.write_text(
        CLEAN.read_text(encoding="utf-8").replace(",925190,", ",25190 ,"),
        encoding="utf-8",
    )
    report2 = validate_path(str(spaced), PROFILE, None, offer_naics_list(str(path2)))
    message = " ".join(f.message for f in report2.findings if f.rule_id == "QP018")
    assert "padded to six characters with a leading zero" in message


# --- a refused list is not a missing list ---------------------------------------------


def test_a_refused_list_leaves_qp018_unevaluated_and_says_which_reason_applies(
    tmp_path: Path,
) -> None:
    """The distinction this project exists to keep.

    "No list was supplied" and "a list was supplied and I would not read it" are
    different facts, and QP018 reports unevaluated under both. If the two carried
    the same reason a filer who mistyped a path would read a paragraph about the
    Commission's publication practice and never learn about their typo.
    """
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"NAICSCode\n111111\n")
    report = validate_path(str(CLEAN), PROFILE, None, offer_naics_list(str(bad)))
    reason = rule_reason(report, "QP018")
    assert reason is not None
    assert str(bad) in reason
    assert "exactly 6 characters" in reason
    assert "resolves to nothing public" not in reason, (
        "the registry's reason is about the Commission and is not what happened here"
    )
    assert report.status is Status.UNVALIDATED
    assert "code_lists" not in json.loads(to_json(report)), (
        "a refused list is not a list the report may claim a rule rested on"
    )


def test_an_unreadable_filing_with_a_list_still_accounts_for_qp018(tmp_path: Path) -> None:
    """The path `_refuse_contradictions` exists to police.

    With a list supplied, QP018 is no longer skipped as unimplemented. A file
    that blocks every rule has to move it into `rules_not_evaluated` like any
    other, or the report applies a rule and mentions it in neither list.
    """
    path = write_list(tmp_path, *CLEAN_CODES)
    report = validate_path(str(FIXTURES / "empty.csv"), PROFILE, None, offer_naics_list(str(path)))
    assert "QP018" in {item.rule_id for item in report.rules_not_evaluated}
    assert "QP018" not in report.rules_evaluated


def test_a_wrong_header_with_a_list_still_accounts_for_qp018(tmp_path: Path) -> None:
    path = write_list(tmp_path, *CLEAN_CODES)
    report = validate_path(
        str(FIXTURES / "wrong_header.csv"), PROFILE, None, offer_naics_list(str(path))
    )
    assert "QP018" in {item.rule_id for item in report.rules_not_evaluated}
    entry = next(e for e in report.evaluation if e.rule_id == "QP018")
    assert entry.blocked_by == "QP002"


# --- the report says so, in both renderings -------------------------------------------


def test_the_json_report_records_the_lists_provenance_and_validates(tmp_path: Path) -> None:
    path = write_list(tmp_path, *CLEAN_CODES)
    report = validate_path(str(CLEAN), PROFILE, None, offer_naics_list(str(path)))
    payload = json.loads(to_json(report))
    record = payload["code_lists"]["naics"]
    assert record["rule"] == "QP018"
    assert record["provenance"] == "caller_supplied"
    assert record["path"] == str(path)
    assert record["codes"] == 3
    assert record["lines"] == 3
    assert "cannot check" in record["note"]
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA_V1.read_text(encoding="utf-8")))
    validator.validate(payload)


def test_the_text_report_says_the_list_was_not_a_published_one(tmp_path: Path) -> None:
    """A reader of this report is not necessarily the person who ran it.

    Every other rule here cites a document that reader can open. This one cites
    a file only the caller has, and the report says so where it cannot be
    missed, rather than only inside a finding a clean filing never prints.
    """
    path = write_list(tmp_path, *CLEAN_CODES)
    report = validate_path(str(CLEAN), PROFILE, None, offer_naics_list(str(path)))
    assert [f for f in report.findings if f.rule_id == "QP018"] == []
    text = to_text(report)
    assert "caller-supplied NAICS code list, not a published one" in text
    assert str(path) in text
    assert report.naics_list is not None
    assert report.naics_list.sha256 in text
    for code in CLEAN_CODES:
        assert code not in text.split("Findings")[0], "a list member reached the header block"


# --- the command line and the Python surface agree ------------------------------------


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "qfer_preflight", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_cli_flag_reaches_the_report(tmp_path: Path) -> None:
    path = write_list(tmp_path, *CLEAN_CODES)
    result = run_cli("check", str(CLEAN), "--naics-list", str(path), "--format", "json")
    payload = json.loads(result.stdout)
    assert payload["code_lists"]["naics"]["sha256"] == load_naics_list(str(path)).sha256


def test_the_cli_says_on_stderr_when_the_list_was_refused(tmp_path: Path) -> None:
    """stdout is the report; a person who mistyped a path is watching stderr.

    The run continues: the other rules are still worth reporting, and QP018
    lands exactly where it lands with no list at all.
    """
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\n")
    result = run_cli("check", str(CLEAN), "--naics-list", str(bad), "--format", "json")
    assert "refused" in result.stderr
    payload = json.loads(result.stdout)
    assert "code_lists" not in payload
    assert payload["status"] == "unvalidated"


def test_a_refused_list_is_non_zero_under_strict(tmp_path: Path) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\n")
    strict = run_cli("check", str(CLEAN), "--naics-list", str(bad), "--strict")
    assert strict.returncode != 0
    plain = run_cli("check", str(CLEAN), "--naics-list", str(bad))
    assert plain.returncode == 0, (
        "a refused list is an unevaluated rule, and an unevaluated rule is not a "
        "finding; --strict is the flag that makes it exit non-zero"
    )


def test_the_python_surface_takes_the_same_list(tmp_path: Path) -> None:
    path = write_list(tmp_path, "111111")
    report = validate(CLEAN, profile="CEC-1306A-S1", naics_list=path)
    assert report.naics_list is not None
    assert report.naics_list.sha256 == load_naics_list(str(path)).sha256
    assert [f for f in report.findings if f.rule_id == "QP018"]


def test_the_python_surface_does_not_raise_on_a_bad_list(tmp_path: Path) -> None:
    """`validate` returns a report for input it could not read rather than raising.

    A refused code list is that promise applied one level out: the caller gets
    the rest of the report and a sentence saying why QP018 did not run.
    """
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"nope\n")
    report = validate(CLEAN, profile="CEC-1306A-S1", naics_list=bad)
    assert report.naics_list is None
    reason = rule_reason(report, "QP018")
    assert reason is not None and str(bad) in reason


def test_a_batch_evaluates_every_input_against_one_list(tmp_path: Path) -> None:
    path = write_list(tmp_path, *CLEAN_CODES)
    result = run_cli("check", str(CLEAN), str(DIRTY), "--naics-list", str(path), "--format", "json")
    payload = json.loads(result.stdout)
    records = [
        entry["report"]["code_lists"]["naics"]["sha256"]
        for entry in payload["results"]
        if "code_lists" in entry["report"]
    ]
    assert len(records) == 2
    assert len(set(records)) == 1, "one list was read once and used for both inputs"


def test_the_rule_registry_still_reports_qp018_as_unimplemented() -> None:
    """`rules` describes the registry, not a run.

    The registry has no NAICS list and never will; a run can be handed one. If
    `rules` started saying QP018 is implemented, it would be claiming this tool
    ships a code set it does not have.
    """
    result = run_cli("rules", "--format", "json")
    registry = {rule["id"]: rule for rule in json.loads(result.stdout)}
    assert registry["QP018"]["implemented"] is False
