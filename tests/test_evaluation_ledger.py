"""The per run ledger: what each rule read, and what it did not.

`rules_evaluated` names the rules that ran. It is true and it is not enough.
A rule can be listed there, correctly, having read every row of a filing and
reached a verdict on none of them, and a reader who sees the identifier
concludes the column was checked. That is the same failure `Findings: none`
represents, one level down, and the ledger exists to make it visible.

What is held here:

  * the arithmetic closes, on every fixture and every profile, so no row can
    be lost between the reader and the report;
  * zero judged is always accompanied by its reason, and a reason never
    appears beside a real count;
  * "ran and judged nothing" is distinguishable from "never ran";
  * the map from rule to column agrees with `docs/column-coverage.md`, in both
    directions, so a rule the registry runs and the ledger never counts fails
    here instead of reporting zero forever;
  * the ledger adds no severity, no finding and no change of verdict.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from qfer_preflight.engine import (
    _FILE_LEVEL_LEDGER_SUBJECTS,
    _Collector,
    _ledger_columns,
    _ledger_slots,
    validate_bytes,
    validate_path,
)
from qfer_preflight.model import (
    LEDGER_SUBJECTS,
    LEDGER_ZERO_REASONS,
    LedgerEntry,
    Report,
    Status,
)
from qfer_preflight.profiles import PROFILES, get_profile
from qfer_preflight.report import to_json, to_text
from qfer_preflight.rules import RULE_SPECS, RULE_SPECS_BY_ID, specs_for

FIXTURES = Path(__file__).parent / "fixtures"
COVERAGE_DOC = Path(__file__).resolve().parents[1] / "docs" / "column-coverage.md"

_RULE_TOKEN = re.compile(r"\bQP[0-9]{3}\b")

# Every clean fixture with the profile it belongs to. These are the files with
# no findings at all, which is exactly where a rule that judged nothing hides.
CLEAN_FIXTURES = [
    ("1306a_s1_clean.csv", "CEC-1306A-S1"),
    ("1306b_clean.csv", "CEC-1306B"),
    ("1308b_s1_clean.csv", "CEC-1308B-S1"),
    ("1308c_clean.csv", "CEC-1308C"),
]


def _check(name: str, profile_id: str) -> Report:
    return validate_path(str(FIXTURES / name), get_profile(profile_id))


def _by_key(report: Report) -> dict[tuple[str, str], LedgerEntry]:
    return {(entry.rule_id, entry.column or ""): entry for entry in report.evaluation}


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture,profile_id", CLEAN_FIXTURES)
def test_every_entry_accounts_for_every_row_it_was_offered(fixture: str, profile_id: str) -> None:
    for entry in _check(fixture, profile_id).evaluation:
        assert entry.judged + entry.exempt + entry.blocked == entry.offered, entry


@pytest.mark.parametrize("fixture,profile_id", CLEAN_FIXTURES)
def test_a_row_rule_is_offered_exactly_the_rows_that_were_read(
    fixture: str, profile_id: str
) -> None:
    """The scope's own test: the ledger's row totals equal `rows_read`.

    Every row rule bound to the form, structural ones included. The two
    exclusions are stated rather than assumed: an entry for a column this form
    does not publish was offered nothing at all, and QP004 is offered the blank
    rows `rows_read` does not count, which is the whole of its subject.
    """
    report = _check(fixture, profile_id)
    assert report.rows_read > 0, "a fixture with no rows would make this vacuous"
    for entry in report.evaluation:
        if entry.subject != "row" or entry.zero_reason == "column_absent":
            continue
        if entry.rule_id == "QP004":
            assert entry.offered >= report.rows_read, entry
            continue
        assert entry.offered == report.rows_read, entry


def test_qp004_is_offered_the_blank_rows_that_rows_read_excludes() -> None:
    """The one rule whose subject is wider than `rows_read`, measured not assumed."""
    report = _check("1306a_s1_dirty.csv", "CEC-1306A-S1")
    blank = _by_key(report)[("QP004", "")]

    assert blank.offered == report.rows_read + 1, (
        "the dirty fixture carries one blank row. If it stopped doing so this "
        "assertion is measuring nothing"
    )
    assert "QP004" in {f.rule_id for f in report.findings}


# ---------------------------------------------------------------------------
# Zero judged, with its reason
# ---------------------------------------------------------------------------


def test_a_zero_is_never_published_without_its_reason() -> None:
    """The assertion this whole feature is for.

    Across every profile and every shape of input the engine can be handed, an
    entry that judged nothing states which of the three reasons applies, and an
    entry that judged something never states one. A zero with no reason beside
    it is indistinguishable from a clean result, which is what the tool exists
    to refuse.
    """
    for profile in PROFILES.values():
        header = ",".join(profile.header)
        payloads = {
            "empty": b"",
            "not utf-8": b"\xff\xfe bad \xc3\x28",
            "wrong header": b"a,b,c\n1,2,3\n",
            "header only": f"{header}\n".encode(),
            "one data row": f"{header}\n{','.join('1' for _ in profile.header)}\n".encode(),
            "short row": f"{header}\n1,2\n".encode(),
            "truncated quote": f'{header}\n"unclosed'.encode(),
            "parse failure": f"{header}\n{'x' * 200_000}\n".encode(),
        }
        for name, payload in payloads.items():
            report = validate_bytes(payload, profile, "x.csv")
            assert report.evaluation, f"{profile.id} on {name!r} published no ledger at all"
            for entry in report.evaluation:
                if entry.judged == 0:
                    assert entry.zero_reason in LEDGER_ZERO_REASONS, (
                        f"{profile.id} on {name!r}: {entry.rule_id} judged nothing "
                        "and does not say why, so the zero reads as a clean result"
                    )
                else:
                    assert entry.zero_reason is None, entry


def test_a_rule_that_ran_and_judged_nothing_is_not_a_rule_that_never_ran() -> None:
    """The distinction a machine reader has to be able to make.

    QP023 on a filing of ordinary NAICS codes ran over every row and judged
    none of them, because the published residential classification table it
    reads has nothing in this file to say anything about. QP023 on a filing
    whose header does not match never ran at all. Both report `judged: 0`.
    """
    ran = _by_key(_check("1308b_s1_clean.csv", "CEC-1308B-S1"))[("QP023", "NAICSCode")]
    never = _by_key(_check("wrong_header.csv", "CEC-1306A-S1"))[("QP023", "NAICSCode")]

    assert ran.judged == never.judged == 0
    assert ran.evaluated is True
    assert ran.zero_reason == "no_applicable_rows"
    assert ran.exempt == 1 and ran.blocked == 0
    assert never.evaluated is False
    assert never.zero_reason == "blocked_by"
    assert never.blocked_by == "QP002"


def test_on_the_wrong_header_fixture_every_column_rule_is_blocked_by_qp002() -> None:
    """The issue's acceptance criterion, asserted over every column rule at once."""
    report = _check("wrong_header.csv", "CEC-1306A-S1")
    column_entries = [e for e in report.evaluation if e.column is not None]

    assert len(column_entries) >= 15, "too few column rules here to be measuring anything"
    for entry in column_entries:
        assert entry.judged == 0, entry
        assert entry.zero_reason == "blocked_by", entry
        assert entry.blocked_by == "QP002", entry
        assert entry.blocked == report.rows_read, entry


def test_an_unreadable_file_names_qp001_as_the_blocker_not_qp002() -> None:
    """A file that never decoded stopped before the header was ever compared."""
    report = validate_bytes(
        b"\xff\xfe\x00\x00not utf-8 \xc3\x28", PROFILES["CEC-1306A-S1"], "x.csv"
    )
    entries = _by_key(report)

    assert entries[("QP002", "")].blocked_by == "QP001"
    assert entries[("QP013", "CountyNumber")].blocked_by == "QP001"
    assert entries[("QP001", "")].judged == 1, "QP001 is the rule that did reach a verdict"


def test_a_short_row_is_blocked_by_qp003_for_that_row_only() -> None:
    """Per row, not per file. One bad row among good ones is one blocked row."""
    profile = PROFILES["CEC-1306A-S1"]
    header = ",".join(profile.header)
    good = "101,2025,1,34,B,A1,925190,10,20,30"
    payload = f"{header}\n{good}\n1,2\n{good}\n".encode()
    entries = _by_key(validate_bytes(payload, profile, "x.csv"))

    county = entries[("QP013", "CountyNumber")]
    assert county.judged == 2
    assert county.blocked == 1
    assert county.blocked_by == "QP003"
    assert county.zero_reason is None, "two rows were judged, so nothing is being explained"


def test_a_header_only_file_says_there_were_no_rows_rather_than_naming_a_blocker() -> None:
    profile = PROFILES["CEC-1306A-S1"]
    payload = ",".join(profile.header).encode() + b"\r\n"
    entry = _by_key(validate_bytes(payload, profile, "x.csv"))[("QP013", "CountyNumber")]

    assert entry.evaluated is True
    assert entry.offered == 0
    assert entry.zero_reason == "no_applicable_rows"
    assert entry.blocked_by is None


def test_a_column_this_form_does_not_publish_says_so() -> None:
    """QP012 reads a Quarter Number, which only Schedule 2 carries."""
    absent = _by_key(_check("1306a_s1_clean.csv", "CEC-1306A-S1"))[("QP012", "")]
    assert absent.zero_reason == "column_absent"
    assert absent.evaluated is False
    assert absent.offered == 0

    present = validate_bytes(
        f"{','.join(get_profile('CEC-1306A-S2').header)}\r\n123,2025,2,Rate A,Text\r\n".encode(),
        get_profile("CEC-1306A-S2"),
        "s2.csv",
    )
    quarter = _by_key(present)[("QP012", "QuarterNumber")]
    assert quarter.judged == 1 and quarter.zero_reason is None


# ---------------------------------------------------------------------------
# Exemption, which is neither a pass nor a failure to run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture,profile_id", CLEAN_FIXTURES)
def test_on_a_clean_file_a_row_rule_judges_every_row_unless_it_states_an_exemption(
    fixture: str, profile_id: str
) -> None:
    """The issue's other acceptance criterion, and the one place it is narrowed.

    Its wording is that every implemented row rule shows judged equal to
    `rows_read` for its columns. That holds for every rule here except the ones
    whose published text does not reach every value, and for those the same
    issue asks for the opposite: it gives "QP023 judged 0 rows because no row
    carried a residential code" as the example the ledger exists to publish. The
    two cannot both be satisfied literally, so what is asserted is the union:
    judged equals `rows_read`, or the shortfall is entirely accounted for by
    exemptions the entry reports.
    """
    report = _check(fixture, profile_id)
    for entry in report.evaluation:
        if entry.column is None or entry.subject != "row":
            continue
        assert entry.judged + entry.exempt == report.rows_read, entry
        assert entry.blocked == 0, "a clean fixture blocks nothing"


def test_the_exemptions_a_clean_run_reports_are_only_the_ones_with_published_grounds() -> None:
    """Named, so a new silent exemption cannot be added without this failing.

    Each of the five sites where a check declines to reach a verdict rests on
    published text or on an ADR, and the ledger is where that now shows. A sixth
    appearing on a clean fixture would mean a rule quietly stopped judging rows.
    """
    exempting = set()
    for fixture, profile_id in CLEAN_FIXTURES:
        report = _check(fixture, profile_id)
        exempting |= {e.rule_id for e in report.evaluation if e.exempt}
    assert exempting == {"QP023"}, (
        "on files with no findings, QP023 is the only rule whose published "
        f"applicability leaves rows untouched. Found {sorted(exempting)}"
    )


def test_the_dirty_fixture_exercises_the_other_exemption_sites() -> None:
    entries = _by_key(_check("1306a_s1_dirty.csv", "CEC-1306A-S1"))

    # A blank company number has no form to be wrong, and is QP021's finding.
    assert entries[("QP033", "CompanyNumber")].exempt == 1
    # "NULL" holds no number for QP020 to read; the footnote QP019 cites covers it.
    assert entries[("QP020", "NumberofCustomers")].exempt == 1


def test_a_padded_county_exempts_qp013_and_is_judged_by_qp024() -> None:
    """ADR 0003 in the ledger: QP013 stands aside rather than reporting a pass."""
    profile = PROFILES["CEC-1306A-S1"]
    header = ",".join(profile.header)
    payload = f"{header}\n101,2025,1,07,B,A1,925190,10,20,30\n".encode()
    entries = _by_key(validate_bytes(payload, profile, "x.csv"))

    assert entries[("QP013", "CountyNumber")].exempt == 1
    assert entries[("QP013", "CountyNumber")].judged == 0
    assert entries[("QP013", "CountyNumber")].zero_reason == "no_applicable_rows"
    assert entries[("QP024", "CountyNumber")].judged == 1


def test_a_workshop_only_customer_type_exempts_qp014_and_is_judged_by_qp025() -> None:
    """ADR 0005 in the ledger, for the value two published documents disagree about."""
    profile = PROFILES["CEC-1306A-S1"]
    header = ",".join(profile.header)
    payload = f"{header}\n101,2025,1,34,O,A1,925190,10,20,30\n".encode()
    entries = _by_key(validate_bytes(payload, profile, "x.csv"))

    assert entries[("QP014", "CustomerType")].exempt == 1
    assert entries[("QP025", "CustomerType")].judged == 1


def test_a_cross_row_rule_cannot_speak_for_a_row_whose_month_was_unreadable() -> None:
    profile = PROFILES["CEC-1306A-S1"]
    header = ",".join(profile.header)
    payload = f"{header}\n101,2025,13,34,B,A1,925190,10,20,30\n".encode()
    entries = _by_key(validate_bytes(payload, profile, "x.csv"))

    quarter_span = entries[("QP030", "Month")]
    assert quarter_span.judged == 0
    assert quarter_span.blocked == 1
    assert quarter_span.blocked_by == "QP011"
    assert quarter_span.zero_reason == "blocked_by"


# ---------------------------------------------------------------------------
# The map, derived from the document that already holds the registry
# ---------------------------------------------------------------------------


def _documented_rules_for_column(profile_id: str, column: str) -> set[str]:
    """The rule identifiers `docs/column-coverage.md` names in one column's row."""
    lines = COVERAGE_DOC.read_text(encoding="utf-8").splitlines()
    inside = False
    for line in lines:
        if line.startswith("## "):
            inside = line[3:].strip() == profile_id
            continue
        if not inside or not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == column:
            return set(_RULE_TOKEN.findall(" ".join(cells[1:])))
    raise AssertionError(f"{COVERAGE_DOC.name} has no row for {column} under {profile_id}")


def test_the_ledger_counts_exactly_the_rules_the_coverage_map_puts_on_each_column() -> None:
    """Both directions, per profile and per column.

    The map is already held against the registry by
    `tests/test_column_coverage.py`. Chaining the ledger to the map rather than
    to the registry directly is deliberate: the map is where a human states
    which rule reads which column, and a ledger that disagrees with it would
    count rows under the wrong heading, or count none at all for a rule that
    runs. The second is the failure this whole file exists to catch, so it may
    not be the failure of the mechanism.
    """
    for profile_id, profile in PROFILES.items():
        for column in profile.header:
            documented = {
                rule_id
                for rule_id in _documented_rules_for_column(profile_id, column)
                if RULE_SPECS_BY_ID[rule_id].implemented
            }
            counted = {
                rule_id
                for rule_id, mapped, _subject, _bound in _ledger_slots(profile)
                if mapped == column
            }
            assert counted == documented, (
                f"{profile_id} column {column}: the ledger counts {sorted(counted)} "
                f"and {COVERAGE_DOC.name} names {sorted(documented)}"
            )


def test_every_implemented_rule_is_placed_somewhere_in_the_ledger_tables() -> None:
    """A newly registered rule cannot be absent from the ledger by being forgotten."""
    for spec in RULE_SPECS:
        if not spec.implemented:
            continue
        if spec.id in _FILE_LEVEL_LEDGER_SUBJECTS:
            assert _FILE_LEVEL_LEDGER_SUBJECTS[spec.id] in LEDGER_SUBJECTS
            continue
        # Raises for a rule neither table places, which is the point.
        _ledger_columns(PROFILES["CEC-1306A-S1"], spec.id)


def test_a_rule_the_ledger_cannot_place_raises_rather_than_reporting_zero() -> None:
    with pytest.raises(ValueError, match="does not know which column it reads"):
        _ledger_columns(PROFILES["CEC-1306A-S1"], "QP999")


def test_the_collector_refuses_rows_counted_against_a_pair_it_does_not_list() -> None:
    """A guard whose raise no test reaches is not a guard.

    A check recording its rows under a misspelled identifier, or under a column
    this form does not carry, would lose every one of them, and the entry it
    meant to fill would report zero judged with a reason invented for it. That
    is the exact defect the ledger was written to expose, so it may not be the
    ledger's own.
    """
    profile = PROFILES["CEC-1306A-S1"]
    collector = _Collector(specs_for(profile), profile)
    collector.judged("QP013", "NoSuchColumn")

    with pytest.raises(ValueError, match="counted rows against QP013/NoSuchColumn"):
        collector.ledger()


def test_qp007_gets_no_entry_where_its_applicability_is_textual_rather_than_columnar() -> None:
    """The one deliberate silence, pinned so it cannot become an accident.

    QP007 applies to the two forms whose instructions publish the words "extra
    headers" and not to the other three (ADR 0007). Giving it a `column_absent`
    entry on those three would state a reason that is not the reason.
    """
    for profile_id, profile in PROFILES.items():
        applies = RULE_SPECS_BY_ID["QP007"].applies(profile)
        listed = any(rule_id == "QP007" for rule_id, _c, _s, _b in _ledger_slots(profile))
        assert listed == applies, f"QP007 on {profile_id}: listed={listed}, applies={applies}"


def test_an_unimplemented_rule_is_left_out_of_the_ledger_and_stays_in_the_other_list() -> None:
    """It reads no row on any file, so a row count for it would count nothing."""
    report = _check("1306a_s1_clean.csv", "CEC-1306A-S1")
    counted = {entry.rule_id for entry in report.evaluation}
    unevaluated = {item.rule_id for item in report.rules_not_evaluated}

    for spec in RULE_SPECS:
        if spec.implemented:
            continue
        assert spec.id not in counted
        assert spec.id in unevaluated, f"{spec.id} would leave no trace at all"


# ---------------------------------------------------------------------------
# The type refuses what the engine must never build
# ---------------------------------------------------------------------------


def _entry(**overrides: object) -> LedgerEntry:
    fields: dict[str, object] = {
        "rule_id": "QP013",
        "column": "CountyNumber",
        "subject": "row",
        "evaluated": True,
        "offered": 3,
        "judged": 3,
        "exempt": 0,
        "blocked": 0,
    }
    fields.update(overrides)
    return LedgerEntry(**fields)  # type: ignore[arg-type]


def test_the_type_refuses_a_ledger_whose_arithmetic_does_not_close() -> None:
    with pytest.raises(ValueError, match="has lost rows somewhere"):
        _entry(offered=4)


def test_the_type_refuses_a_zero_with_no_reason() -> None:
    with pytest.raises(ValueError, match="A reason is stated"):
        _entry(offered=0, judged=0)


def test_the_type_refuses_a_reason_beside_a_real_count() -> None:
    with pytest.raises(ValueError, match="A reason is stated"):
        _entry(zero_reason="no_applicable_rows")


def test_the_type_refuses_a_reason_outside_the_closed_vocabulary() -> None:
    with pytest.raises(ValueError, match="closed vocabulary"):
        _entry(offered=0, judged=0, zero_reason="looked_fine")


def test_the_type_refuses_a_block_that_does_not_name_the_rule_that_blocked_it() -> None:
    with pytest.raises(ValueError, match="does not name the rule that blocked"):
        _entry(judged=2, blocked=1)


def test_the_type_refuses_a_blocker_named_where_nothing_was_blocked() -> None:
    with pytest.raises(ValueError, match="while reporting nothing blocked"):
        _entry(blocked_by="QP002")


def test_the_type_refuses_a_subject_a_reader_cannot_look_up() -> None:
    with pytest.raises(ValueError, match="not one of"):
        _entry(subject="cell")


def test_the_type_refuses_a_negative_count() -> None:
    with pytest.raises(ValueError, match="counts -1"):
        _entry(offered=2, judged=3, exempt=-1)


def test_the_type_accepts_the_shapes_the_engine_really_produces() -> None:
    """A constructor that refused everything would be as useless as one that refused nothing."""
    _entry()
    _entry(offered=0, judged=0, zero_reason="column_absent", column=None)
    _entry(judged=0, exempt=3, zero_reason="no_applicable_rows")
    _entry(judged=0, blocked=3, exempt=0, zero_reason="blocked_by", blocked_by="QP002")


# ---------------------------------------------------------------------------
# The ledger changes nothing about the verdict
# ---------------------------------------------------------------------------


def test_the_ledger_adds_no_finding_no_advisory_and_no_severity() -> None:
    """It is a measurement of the run. Its presence must move nothing."""
    report = _check("1306a_s1_clean.csv", "CEC-1306A-S1")

    assert report.evaluation, "the fixture stopped producing a ledger"
    assert any(entry.judged == 0 for entry in report.evaluation)
    assert report.findings == []
    assert report.advisories == []
    assert report.status is Status.UNVALIDATED
    assert not hasattr(report.evaluation[0], "severity")


def test_the_ledger_survives_the_json_rendering_intact() -> None:
    report = _check("1306a_s1_dirty.csv", "CEC-1306A-S1")
    payload = json.loads(to_json(report))
    rendered = {(e["rule_id"], e["column"] or ""): e for e in payload["evaluation"]}

    assert len(rendered) == len(report.evaluation)
    for key, entry in _by_key(report).items():
        assert rendered[key]["judged"] == entry.judged
        assert rendered[key]["offered"] == entry.offered
        assert ("zero_reason" in rendered[key]) == (entry.zero_reason is not None)
        # Written even when null, so the table has the same cells in every row.
        assert "column" in rendered[key]


def test_the_json_ledger_is_ordered_and_therefore_reproducible() -> None:
    first = json.loads(to_json(_check("1306a_s1_clean.csv", "CEC-1306A-S1")))["evaluation"]
    second = json.loads(to_json(_check("1306a_s1_clean.csv", "CEC-1306A-S1")))["evaluation"]
    keys = [(entry["rule_id"], entry["column"] or "") for entry in first]

    assert first == second
    assert keys == sorted(keys)


def test_the_text_rendering_prints_the_reason_beside_every_zero() -> None:
    text = to_text(_check("1308b_s1_clean.csv", "CEC-1308B-S1"))
    ledger = text.split("Evaluation ledger")[1]

    assert "QP023  NAICSCode" in ledger
    assert "judged nothing: no row fell inside its published applicability" in ledger
    assert "this form publishes no column it reads" in ledger
    for line in ledger.splitlines():
        if " judged 0 of " in line:
            assert "judged nothing:" in line, f"a bare zero was printed: {line!r}"


def test_the_text_rendering_says_the_ledger_decides_nothing() -> None:
    text = to_text(_check("1306a_s1_clean.csv", "CEC-1306A-S1"))
    assert "adds no severity" in text
    assert "changes no verdict" in text


def test_a_report_with_no_ledger_prints_no_ledger_table() -> None:
    """A hand-built report took no measurement, so it states none."""
    bare = Report(
        tool="qfer-preflight",
        tool_version="0.0.0",
        profile_id="CEC-1306A-S1",
        profile_title="t",
        input_name="x.csv",
        input_sha256="0" * 64,
    )
    assert "Evaluation ledger" not in to_text(bare)
    assert json.loads(to_json(bare))["evaluation"] == []
