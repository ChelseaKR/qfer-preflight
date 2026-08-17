"""What a report does when the same thing is wrong with every row.

A quarterly UDC filing runs to hundreds of thousands of rows. One wrong county
number in a mapping table puts the same finding on all of them, and a report
that prints it once per row is a report nobody reads: the filer scrolls, gives
up, and learns nothing the first line did not already tell them.

The answer here is to merge findings that are identical and say so. The tests
below hold that merge to the only terms on which it is acceptable:

  * it never merges two findings that say different things;
  * it never loses the count, the first rows, or the last row;
  * it never happens silently, in either output format.

The last one matters most. This tool exists because validators that quietly
skip things read the same as validators that checked them, and a report that
quietly drops findings is the same defect wearing a different hat.
"""

from __future__ import annotations

import json

import pytest

from qfer_preflight.engine import validate_bytes
from qfer_preflight.model import Finding, Report, Severity
from qfer_preflight.profiles import PROFILE_1306A_S1
from qfer_preflight.report import _LINES_PER_RULE_AND_COLUMN, to_json, to_text

HEADER = ",".join(PROFILE_1306A_S1.header)
GOOD_ROW = "101,2025,1,34,B,A1,925190,1200,4500000,675000.25"


def _check(body: str) -> Report:
    return validate_bytes(body.encode(), PROFILE_1306A_S1, "input.csv")


def _same_bad_county(count: int, county: str = "77") -> Report:
    rows = "\n".join(f"101,2025,1,{county},B,A1,925190,1200,4500000,1" for _ in range(count))
    return _check(f"{HEADER}\n{rows}\n")


def _distinct_bad_counties(count: int) -> Report:
    """Every row wrong, every row wrong differently, so nothing may merge."""
    rows = "\n".join(f"101,2025,1,{60 + i},B,A1,925190,1200,4500000,1" for i in range(count))
    return _check(f"{HEADER}\n{rows}\n")


# ---------------------------------------------------------------------------
# The merge itself
# ---------------------------------------------------------------------------


def test_the_same_finding_on_every_row_is_reported_once() -> None:
    report = _same_bad_county(5_000)

    counties = [f for f in report.findings if f.rule_id == "QP013"]
    assert len(counties) == 1, "5,000 copies of one sentence is not a report"
    assert counties[0].occurrences == 5_000


def test_a_merged_finding_keeps_the_count_and_the_span() -> None:
    """Merging may drop nothing a filer would have used."""
    finding = next(f for f in _same_bad_county(5_000).findings if f.rule_id == "QP013")

    assert finding.occurrences == 5_000
    assert finding.row == 2, "the first offending row is still named"
    assert finding.cell == "D2"
    assert finding.example_rows == (2, 3, 4, 5, 6)
    assert finding.last_row == 5_001, "the far end of the run is still named"


def test_error_counts_report_rows_not_lines() -> None:
    """A filer asking how many errors they have means rows, not paragraphs."""
    report = _same_bad_county(5_000)

    assert report.error_count == 5_000
    assert report.finding_count == 5_000
    assert len(report.findings) == 1
    assert report.merged_finding_count == 4_999


def test_findings_that_differ_are_never_merged() -> None:
    """The merge key includes the message, so a different value is a different line."""
    report = _distinct_bad_counties(30)

    counties = [f for f in report.findings if f.rule_id == "QP013"]
    assert len(counties) == 30
    assert all(f.occurrences == 1 for f in counties)
    assert len({f.message for f in counties}) == 30


def test_two_columns_with_the_same_problem_stay_apart() -> None:
    """The column is part of the key, so one line may not speak for two columns."""
    rows = "\n".join("101,2025,1,34,B,A1,925190,NULL,NULL,1" for _ in range(50))
    report = _check(f"{HEADER}\n{rows}\n")

    columns = {f.column for f in report.findings if f.rule_id == "QP019"}
    assert len(columns) == 2, columns
    assert all(f.occurrences == 50 for f in report.findings if f.rule_id == "QP019")


def test_a_finding_seen_once_carries_no_repeat_bookkeeping() -> None:
    report = _check(f"{HEADER}\n101,2025,1,77,B,A1,925190,1200,4500000,1\n")
    finding = next(f for f in report.findings if f.rule_id == "QP013")

    assert finding.occurrences == 1
    assert finding.example_rows == ()
    assert finding.last_row is None
    assert "occurrences" not in finding.to_dict()


# ---------------------------------------------------------------------------
# Saying what was collapsed
# ---------------------------------------------------------------------------


def test_the_text_report_states_what_it_merged() -> None:
    text = to_text(_same_bad_county(5_000))

    assert "standing for 5,000 findings" in text
    assert "The same finding appears on 5,000 rows" in text
    assert "from row 2 to row 5,001" in text
    assert "Collapsed: 4,999 findings" in text
    assert "no distinct problem was hidden" in text


def test_a_report_with_nothing_to_merge_says_nothing_about_merging() -> None:
    text = to_text(_check(f"{HEADER}\n101,2025,1,77,B,A1,925190,1200,4500000,1\n"))

    assert "Collapsed:" not in text
    assert "standing for" not in text
    assert "Findings (1):" in text


def test_the_json_report_states_the_merge_policy_and_the_count() -> None:
    payload = json.loads(to_json(_same_bad_county(5_000)))

    assert payload["collapsed"]["identical_findings_merged"] == 4_999
    assert "No finding is dropped" in payload["collapsed"]["policy"]
    assert payload["counts"]["findings"] == 5_000
    assert payload["counts"]["finding_lines"] == 1
    entry = next(f for f in payload["findings"] if f["rule_id"] == "QP013")
    assert entry["occurrences"] == 5_000
    assert entry["example_rows"] == [2, 3, 4, 5, 6]
    assert entry["last_row"] == 5_001


def test_a_clean_report_declares_a_merge_count_of_zero() -> None:
    """The key is always present, so a reader never has to infer its absence."""
    payload = json.loads(to_json(_check(f"{HEADER}\n{GOOD_ROW}\n")))
    assert payload["collapsed"]["identical_findings_merged"] == 0


def test_a_few_repeats_are_listed_in_full_rather_than_summarised() -> None:
    text = to_text(_same_bad_county(3))
    assert "The same finding appears on 3 rows: rows 2, 3, 4." in text


# ---------------------------------------------------------------------------
# The one place the text rendering stops short, and how loudly it says so
# ---------------------------------------------------------------------------


def test_the_text_report_stops_listing_distinct_findings_and_says_it_did() -> None:
    """Distinct messages cannot merge, so the text has to draw a line somewhere.

    It draws it per rule and column, states the number it did not print, and
    names the format that still holds all of them. What it must never do is
    stop quietly.
    """
    report = _distinct_bad_counties(30)
    text = to_text(report)

    listed = text.count("  [ERROR] QP013  cell D")
    assert listed == _LINES_PER_RULE_AND_COLUMN
    assert "30 lines" in text
    assert "10 listed below" in text
    assert "20 further findings in column CountyNumber are not listed here" in text
    assert "--format json for every one" in text


def test_the_json_report_withholds_nothing_the_text_report_stopped_at() -> None:
    """The escape hatch has to actually hold everything, or it is not one."""
    report = _distinct_bad_counties(30)
    payload = json.loads(to_json(report))

    counties = [f for f in payload["findings"] if f["rule_id"] == "QP013"]
    assert len(counties) == 30
    assert len({f["message"] for f in counties}) == 30


def test_a_report_under_the_limit_prints_every_line() -> None:
    report = _distinct_bad_counties(_LINES_PER_RULE_AND_COLUMN)
    text = to_text(report)

    assert "not listed here" not in text
    assert text.count("  [ERROR] QP013  cell D") == _LINES_PER_RULE_AND_COLUMN


def test_the_limit_is_per_rule_and_column_not_per_report() -> None:
    """A second rule's findings are not suppressed by the first rule's volume."""
    rows = "\n".join(
        f"101,2025,1,{60 + i},X,A1,925190,1200,4500000,1"
        for i in range(_LINES_PER_RULE_AND_COLUMN + 5)
    )
    text = to_text(_check(f"{HEADER}\n{rows}\n"))

    assert "  [ERROR] QP014" in text, "the customer type finding must still be printed"
    assert "5 further findings in column CountyNumber" in text


# ---------------------------------------------------------------------------
# The model guards behind all of it
# ---------------------------------------------------------------------------


def test_a_finding_cannot_claim_fewer_than_one_occurrence() -> None:
    with pytest.raises(ValueError, match="occurrences"):
        Finding("QP013", Severity.ERROR, "m", occurrences=0)


def test_a_finding_cannot_list_more_examples_than_it_has_occurrences() -> None:
    """Otherwise a line could stand for fewer rows than it names."""
    with pytest.raises(ValueError, match="more example rows"):
        Finding("QP013", Severity.ERROR, "m", occurrences=2, example_rows=(2, 3, 4))


def test_a_large_run_of_identical_findings_is_bounded_work() -> None:
    """The merge happens as findings are gathered, not when they are rendered.

    Holding one object per bad cell would mean 200,000 copies of the same
    three hundred character sentence before anything got the chance to
    summarise them. This asserts the shape rather than the memory: one group,
    five example rows, whatever the row count.
    """
    report = _same_bad_county(200_000)

    assert len(report.findings) == 1
    assert report.findings[0].occurrences == 200_000
    assert len(report.findings[0].example_rows) == 5
    assert report.rows_read == 200_000
