"""Deliberately hostile input, and what the report is willing to say about it.

`tests/test_fail_closed.py` guards the contract from the front: a file the tool
could not read must not report like one it could. This file attacks the same
contract from behind, by feeding the reader input that is broken in ways a
naive validator does not notice at all.

The question asked of every case here is not "did it find the problem". It is
"was the report honest about what it did and did not evaluate". A file that is
truncated, or whose cells begin with an equals sign, or whose Month is a
fullwidth digit, used to come back with an empty finding list. Nothing in the
output distinguished it from a well-formed filing. Each of those is a case
below, and each one asserts that the silence is gone.
"""

from __future__ import annotations

import pytest

from qfer_preflight.engine import _unterminated_quote, validate_bytes
from qfer_preflight.model import Report, Status
from qfer_preflight.profiles import PROFILE_1306A_S1, PROFILE_1306B
from qfer_preflight.report import to_json, to_text

HEADER = ",".join(PROFILE_1306A_S1.header)
GOOD_ROW = "101,2025,1,34,B,A1,925190,1200,4500000,675000.25"


def _check(body: str | bytes, profile: object = PROFILE_1306A_S1) -> Report:
    data = body.encode() if isinstance(body, str) else body
    return validate_bytes(data, profile, "input.csv")  # type: ignore[arg-type]


def _rule_ids(report: Report) -> set[str]:
    return {finding.rule_id for finding in report.findings}


def _advisory_codes(report: Report) -> set[str]:
    return {advisory.code for advisory in report.advisories}


def _says_something(report: Report) -> bool:
    """Whether the report draws attention to anything at all.

    This is the property under test throughout the file. A report that has no
    findings and no advisories reads as a clean bill of health, whatever the
    status line above it says, because the body is empty.
    """
    return bool(report.findings or report.advisories)


# ---------------------------------------------------------------------------
# The blanket assertion: no adversarial input may come back quiet
# ---------------------------------------------------------------------------

CASES: dict[str, bytes] = {
    "truncated mid line": f"{HEADER}\n{GOOD_ROW}\n101,2025,2,34,B,A1,9251".encode(),
    "truncated inside a quoted value": f'{HEADER}\n101,2025,1,34,B,A1,925190,15,22000,"3100'.encode(),
    "mixed line endings": f"{HEADER}\r\n{GOOD_ROW}\n{GOOD_ROW}\r".encode(),
    "carriage return line endings": f"{HEADER}\r{GOOD_ROW}\r".encode(),
    "utf-8 byte order mark": b"\xef\xbb\xbf" + f"{HEADER}\n{GOOD_ROW}\n".encode(),
    "header and no data rows": f"{HEADER}\n".encode(),
    "header with no trailing newline": HEADER.encode(),
    "header and blank rows only": f"{HEADER}\n\n\n,,,,,,,,,\n".encode(),
    "duplicated header column": f"{HEADER},Revenue\n{GOOD_ROW},1\n".encode(),
    "header row repeated as data": f"{HEADER}\n{GOOD_ROW}\n{HEADER}\n".encode(),
    "not utf-8": f"{HEADER}\n101,2025,1,34,B,A\xe9,925190,1,1,1\n".encode("latin-1"),
    "utf-16": f"{HEADER}\n{GOOD_ROW}\n".encode("utf-16"),
    "formula in a text column": f"{HEADER}\n=1+1,2025,1,34,B,A1,925190,1200,4500000,1\n".encode(),
    "at sign formula": f"{HEADER}\n101,2025,1,34,B,@SUM(A1:A9),925190,1,1,1\n".encode(),
    "formula in a numeric column": f"{HEADER}\n101,2025,1,34,B,A1,925190,=1+1,1,1\n".encode(),
    "NUL byte in a value": f"{HEADER}\n101,2025,1,34,B,A1,RE11\x0000,1,1,1\n".encode(),
    "newline inside a quoted value": f'{HEADER}\n101,2025,1,34,B,"A1\nA2",925190,1,1,1\n'.encode(),
    "whitespace only": b"   \n\t\n   \n",
    "binary": bytes(range(256)) * 4,
    "prose, not csv": b"this is not a csv at all\njust prose\n",
    "tab separated": f"{HEADER}\n{GOOD_ROW}\n".replace(",", "\t").encode(),
    "semicolon separated": f"{HEADER}\n{GOOD_ROW}\n".replace(",", ";").encode(),
    "fullwidth digit month": f"{HEADER}\n101,2025,\uff11,34,B,A1,925190,1,1,1\n".encode(),
    "arabic-indic digit year": f"{HEADER}\n101,\u0662\u0660\u0662\u0665,1,34,B,A1,925190,1,1,1\n".encode(),
    "non-breaking space in a code": f"{HEADER}\n101,2025,1,34,B\xa0,A1,925190,1,1,1\n".encode(),
    "field over the csv size limit": f"{HEADER}\n101,2025,1,34,B,{'A' * 200_000},925190,1,1,1\n".encode(),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_no_adversarial_input_produces_a_silent_report(name: str) -> None:
    """The core promise. None of these may come back with nothing to say."""
    report = _check(CASES[name])
    assert _says_something(report), (
        f"{name!r} produced a report with no findings and no advisories, which "
        "reads as a clean file"
    )


@pytest.mark.parametrize("name", sorted(CASES))
def test_no_adversarial_input_is_ever_reported_as_a_pass(name: str) -> None:
    report = _check(CASES[name])
    assert report.status is not Status.PASS


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_adversarial_input_fails_strict(name: str) -> None:
    """`--strict` gates on the status, so nothing here may reach status pass."""
    report = _check(CASES[name])
    assert report.status in (Status.FAIL, Status.UNVALIDATED)


@pytest.mark.parametrize("name", sorted(CASES))
def test_adversarial_reports_render_in_both_formats(name: str) -> None:
    report = _check(CASES[name])
    assert to_json(report).endswith("\n")
    text = to_text(report)
    assert "status  :" in text
    if report.advisories:
        assert "These are not CEC rules" in text


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


def test_a_file_cut_off_inside_a_quoted_value_is_an_error_not_a_pass() -> None:
    """The case Python's CSV reader hides.

    `csv.reader` reaches the end of the input inside an open quoted field,
    hands back what it accumulated, and raises nothing. Before this was
    detected the report showed two data rows, zero findings and exit zero on a
    file that had been cut in half.
    """
    report = _check(f'{HEADER}\n{GOOD_ROW}\n101,2025,2,34,B,A1,925190,15,22000,"3100')

    assert report.status is Status.FAIL
    assert "QP001" in _rule_ids(report)
    assert report.rows_read == 0
    assert report.rules_evaluated == ["QP001"], (
        "a truncated file must leave every other rule unevaluated, because the "
        "reader cannot know what the missing part would have said"
    )
    message = next(f.message for f in report.findings if f.rule_id == "QP001")
    assert "cut off" in message


def test_a_complete_file_with_quoted_values_is_not_called_truncated() -> None:
    """The truncation check must not fire on ordinary quoting."""
    body = f'{HEADER}\n101,2025,1,34,B,"A,1",925190,1200,4500000,"675,000.25"\n'
    report = _check(body)
    assert "QP001" not in _rule_ids(report)


def test_a_quotation_mark_inside_an_unquoted_value_is_not_truncation() -> None:
    """A stray quote mid-field does not open a quoted field, so it is not a cut."""
    report = _check(f'{HEADER}\n101,2025,1,34,B,A1"x,925190,1200,4500000,1\n')
    assert "QP001" not in _rule_ids(report)


def test_an_escaped_quotation_mark_is_not_truncation() -> None:
    report = _check(f'{HEADER}\n101,2025,1,34,B,"A""1",925190,1200,4500000,1\n')
    assert "QP001" not in _rule_ids(report)


def test_no_well_formed_csv_is_ever_called_truncated() -> None:
    """The property that keeps the truncation check from crying wolf.

    A false positive here is the worst outcome in the file: QP001 blocks every
    other rule, so one would turn a readable filing into a report that says
    nothing was checked. Rather than trust a hand-picked set of examples, this
    generates documents with the standard library's own CSV writer, whose
    output is well formed by construction, and asserts the check stays quiet.
    Values are drawn from the characters that make quoting necessary: commas,
    quotation marks, newlines and tabs.
    """
    import csv
    import io
    import random

    awkward = ["a", "1", ",", '"', " ", "\n", "\r", "\t", ";"]
    rng = random.Random(7)

    for _ in range(2000):
        rows = [
            [
                "".join(rng.choice(awkward) for _ in range(rng.randint(0, 6)))
                for _ in range(rng.randint(1, 4))
            ]
            for _ in range(rng.randint(1, 4))
        ]
        buffer = io.StringIO(newline="")
        csv.writer(buffer, lineterminator=rng.choice(["\n", "\r\n"])).writerows(rows)
        text = buffer.getvalue()
        assert not _unterminated_quote(text), repr(text)


@pytest.mark.parametrize(
    "text",
    [
        '"abc',
        'a,"abc',
        'a,b\n"',
        '"a""b',
        'x\n"unfinished, with a comma',
    ],
)
def test_an_open_quoted_field_is_detected(text: str) -> None:
    assert _unterminated_quote(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "a,b\n",
        '"a","b"\n',
        '"a,b"\n',
        'a"b,c\n',
        '"a""b"\n',
        '"multi\nline"\n',
    ],
)
def test_a_closed_document_is_not_detected(text: str) -> None:
    assert not _unterminated_quote(text)


def test_a_row_cut_off_mid_line_is_reported_as_a_short_row() -> None:
    report = _check(f"{HEADER}\n{GOOD_ROW}\n101,2025,2,34,B,A1,9251")
    assert "QP003" in _rule_ids(report)
    message = next(f.message for f in report.findings if f.rule_id == "QP003")
    assert "NumberofCustomers" in message, "a short row should name the columns it stops before"


# ---------------------------------------------------------------------------
# Parse failure part way through
# ---------------------------------------------------------------------------


def test_a_parse_failure_discards_the_findings_from_the_readable_prefix() -> None:
    """A file that stops parsing has not been checked, not even the good part.

    Keeping the findings gathered before the failure would invite reading the
    prefix as validated. It was not: the reader has no idea what the rest of
    the file would have said about those same rows.
    """
    oversized = "A" * 200_000
    body = f"{HEADER}\n101,2025,13,77,X,A1,12345,1,1,1\n101,2025,1,34,B,{oversized},925190,1,1,1\n"
    report = _check(body)

    assert report.status is Status.FAIL
    assert _rule_ids(report) == {"QP001"}
    assert report.rows_read == 0
    assert report.rules_evaluated == ["QP001"]
    message = next(f.message for f in report.findings if f.rule_id == "QP001")
    assert "field larger than field limit" in message, "the reader's own reason should survive"
    assert "including the rows before" in message


# ---------------------------------------------------------------------------
# Encoding and byte order marks
# ---------------------------------------------------------------------------


def test_a_byte_order_mark_is_disclosed_rather_than_silently_removed() -> None:
    """The reader strips it. A filer whose portal does not needs to know."""
    report = _check(b"\xef\xbb\xbf" + f"{HEADER}\n{GOOD_ROW}\n".encode())

    assert "ADV-BOM" in _advisory_codes(report)
    assert report.status is Status.UNVALIDATED
    assert "QP002" not in _rule_ids(report), "the reader still matched the header"


def test_a_file_holding_only_a_byte_order_mark_says_so() -> None:
    report = _check(b"\xef\xbb\xbf")
    message = next(f.message for f in report.findings if f.rule_id == "QP001")
    assert "byte order mark" in message
    assert "The file is empty." not in message, "it is not empty, it holds three bytes"


def test_a_whitespace_only_file_is_not_described_as_empty() -> None:
    report = _check(b"   \n\t\n   \n")
    message = next(f.message for f in report.findings if f.rule_id == "QP001")
    assert "whitespace" in message
    assert report.rules_evaluated == ["QP001"]


def test_a_decode_failure_names_the_offending_byte() -> None:
    report = _check("101,2025,1,34,B,A\xe9,925190,1,1,1\n".encode("latin-1"))
    message = next(f.message for f in report.findings if f.rule_id == "QP001")
    assert "byte 17" in message, message
    assert "0xE9" in message
    assert report.rules_evaluated == ["QP001"]


# ---------------------------------------------------------------------------
# Line endings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        f"{HEADER}\r\n{GOOD_ROW}\n{GOOD_ROW}\r",
        f"{HEADER}\r{GOOD_ROW}\r",
        f"{HEADER}\n101,2025,1,34,B,A\r1,925190,1,1,1\n",
    ],
)
def test_unusual_line_endings_are_disclosed(body: str) -> None:
    report = _check(body)
    assert "ADV-LINE-ENDINGS" in _advisory_codes(report)


@pytest.mark.parametrize("terminator", ["\n", "\r\n"])
def test_a_file_with_one_ordinary_line_ending_raises_no_advisory(terminator: str) -> None:
    report = _check(f"{HEADER}{terminator}{GOOD_ROW}{terminator}")
    assert "ADV-LINE-ENDINGS" not in _advisory_codes(report)


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------


def test_a_duplicated_header_column_fails_the_header_check() -> None:
    report = _check(f"{HEADER},Revenue\n{GOOD_ROW},1\n")
    assert "QP002" in _rule_ids(report)
    for rule_id in ("QP010", "QP013", "QP014", "QP020"):
        assert rule_id not in report.rules_evaluated


def test_every_profile_header_has_unique_column_names() -> None:
    """`index_of` returns the first match, so a repeat would silently misroute."""
    from qfer_preflight.profiles import PROFILES

    for profile in PROFILES.values():
        assert len(set(profile.header)) == len(profile.header), profile.id


def test_a_header_only_file_names_what_to_do_about_it() -> None:
    report = _check(f"{HEADER}\n")
    message = next(f.message for f in report.findings if f.rule_id == "QP006")
    assert "add one row" in message


def test_a_repeated_header_row_is_explained_rather_than_only_flagged() -> None:
    """Eight confusing errors become one obvious fix."""
    report = _check(f"{HEADER}\n{GOOD_ROW}\n{HEADER}\n")
    assert "ADV-REPEATED-HEADER" in _advisory_codes(report)
    advisory = next(a for a in report.advisories if a.code == "ADV-REPEATED-HEADER")
    assert advisory.row == 3
    assert "copy of the header row" in advisory.message


def test_a_tab_separated_file_is_told_it_is_tab_separated() -> None:
    report = _check(f"{HEADER}\n{GOOD_ROW}\n".replace(",", "\t"))
    message = next(f.message for f in report.findings if f.rule_id == "QP002")
    assert "tabs" in message
    assert "comma separated values" in message
    assert "missing column names" not in message, "one long cell needs no column by column list"


def test_a_semicolon_separated_file_is_told_which_character_it_used() -> None:
    report = _check(f"{HEADER}\n{GOOD_ROW}\n".replace(",", ";"))
    assert "semicolons" in next(f.message for f in report.findings if f.rule_id == "QP002")


def test_a_header_padded_with_spaces_gets_one_sentence_not_ten() -> None:
    padded = " , ".join(PROFILE_1306A_S1.header)
    report = _check(f"{padded}\n{GOOD_ROW}\n")
    message = next(f.message for f in report.findings if f.rule_id == "QP002")
    assert "apart from whitespace around them" in message
    assert message.count("column A:") == 0, "the summary replaces the per column list"


def test_a_header_in_the_wrong_case_says_so() -> None:
    shouted = ",".join(name.upper() for name in PROFILE_1306A_S1.header)
    report = _check(f"{shouted}\n{GOOD_ROW}\n")
    message = next(f.message for f in report.findings if f.rule_id == "QP002")
    assert "capitalisation" in message


def test_a_reordered_header_says_the_order_is_wrong() -> None:
    swapped = list(PROFILE_1306A_S1.header)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    report = _check(",".join(swapped) + f"\n{GOOD_ROW}\n")
    message = next(f.message for f in report.findings if f.rule_id == "QP002")
    assert "different position" in message


def test_a_header_report_always_ends_with_the_template_line() -> None:
    report = _check("Company,Year,Month\n1,2025,1\n")
    message = next(f.message for f in report.findings if f.rule_id == "QP002")
    assert message.endswith(",".join(PROFILE_1306A_S1.header))


# ---------------------------------------------------------------------------
# Formula injection and hidden characters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "row",
    [
        "=1+1,2025,1,34,B,A1,925190,1200,4500000,1",
        "101,2025,1,34,B,\"=cmd|'/C calc'!A0\",925190,1200,4500000,1",
        "101,2025,1,34,B,@SUM(A1:A9),925190,1200,4500000,1",
        "-2+3,2025,1,34,B,A1,925190,1200,4500000,1",
        '="0101",2025,1,34,B,A1,925190,1200,4500000,1',
        "101,2025,1,34,B,\tA1,925190,1200,4500000,1",
    ],
)
def test_a_formula_payload_is_never_silent(row: str) -> None:
    """A cell a spreadsheet will execute must not leave an empty report."""
    report = _check(f"{HEADER}\n{row}\n")
    assert "ADV-FORMULA-CELL" in _advisory_codes(report)
    assert report.status is not Status.PASS


def test_the_formula_advisory_says_it_is_not_a_cec_rule() -> None:
    report = _check(f"{HEADER}\n=1+1,2025,1,34,B,A1,925190,1200,4500000,1\n")
    advisory = next(a for a in report.advisories if a.code == "ADV-FORMULA-CELL")
    assert "No published CEC document addresses this" in advisory.message


@pytest.mark.parametrize("value", ["-24", "+10", "1200", "-3.5", "675000.25"])
def test_an_ordinary_signed_amount_raises_no_formula_advisory(value: str) -> None:
    """A leading minus is how a negative amount is written. It is not a payload."""
    report = _check(f"{HEADER}\n101,2025,1,34,B,A1,925190,1200,4500000,{value}\n")
    assert "ADV-FORMULA-CELL" not in _advisory_codes(report)


def test_a_hidden_character_in_an_unchecked_column_is_disclosed() -> None:
    report = _check(f'{HEADER}\n101,2025,1,34,B,"A1\nA2",925190,1200,4500000,1\n')
    assert "ADV-HIDDEN-CHARACTER" in _advisory_codes(report)
    advisory = next(a for a in report.advisories if a.code == "ADV-HIDDEN-CHARACTER")
    assert "line feed" in advisory.message


def test_a_hidden_character_a_rule_already_caught_is_not_repeated() -> None:
    """The advisory claims no rule covers the column, so it must stay true."""
    report = _check(f"{HEADER}\n101,2025,1,34,B\xa0,A1,925190,1200,4500000,1\n")
    assert "QP014" in _rule_ids(report)
    hidden = [a for a in report.advisories if a.column == "CustomerType"]
    assert hidden == []


def test_advisories_are_capped_rather_than_repeated_for_every_row() -> None:
    rows = "\n".join("=1,2025,1,34,B,A1,925190,1,1,1" for _ in range(200))
    report = _check(f"{HEADER}\n{rows}\n")
    formula = [a for a in report.advisories if a.code == "ADV-FORMULA-CELL"]
    assert len(formula) <= 7, "200 identical advisories would bury the report"
    assert any(a.occurrences == 200 for a in formula), "the total must still be reported"


# ---------------------------------------------------------------------------
# Digits that are not digits
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "row,expected_rule",
    [
        ("101,2025,\uff11,34,B,A1,925190,1,1,1", "QP011"),
        ("101,\u0662\u0660\u0662\u0665,1,34,B,A1,925190,1,1,1", "QP010"),
        ("101,2025,1,34,B,A1,925190,\u0661\u0662,1,1", "QP020"),
        ("101,2025,\u0665,34,B,A1,925190,1,1,1", "QP011"),
    ],
)
def test_a_unicode_digit_is_not_accepted_as_a_number(row: str, expected_rule: str) -> None:
    """Python's `\\d` matches every Unicode decimal digit, and `int()` converts it.

    A Month of U+FF11 and a Year of U+0662 U+0660 U+0662 U+0665 both used to
    pass with no finding, because the pattern accepted them and int() agreed.
    No portal would.
    """
    report = _check(f"{HEADER}\n{row}\n")
    assert expected_rule in _rule_ids(report)


def test_a_unicode_digit_finding_explains_what_is_wrong_with_it() -> None:
    report = _check(f"{HEADER}\n101,2025,\uff11,34,B,A1,925190,1,1,1\n")
    message = next(f.message for f in report.findings if f.rule_id == "QP011")
    assert "not a plain 0 to 9 digit" in message
    assert "U+FF11" in message


# ---------------------------------------------------------------------------
# Size
# ---------------------------------------------------------------------------


def test_a_large_file_is_read_without_holding_every_row_at_once() -> None:
    rows = "\n".join(GOOD_ROW for _ in range(20_000))
    report = _check(f"{HEADER}\n{rows}\n")
    assert report.rows_read == 20_000
    assert report.findings == []
    assert report.status is Status.UNVALIDATED


def test_a_bad_row_deep_in_a_large_file_is_still_found() -> None:
    rows = "\n".join(GOOD_ROW for _ in range(10_000))
    report = _check(f"{HEADER}\n{rows}\n101,2025,1,77,X,A1,12345,NULL,1,1\n")
    assert {"QP013", "QP014", "QP017", "QP019"} <= _rule_ids(report)
    assert next(f for f in report.findings if f.rule_id == "QP013").row == 10_002


# ---------------------------------------------------------------------------
# Reports stay distinguishable
# ---------------------------------------------------------------------------


def test_each_adversarial_report_differs_from_the_clean_one() -> None:
    """The fail closed digest property, extended across the whole corpus."""
    clean = to_json(_check(f"{HEADER}\n{GOOD_ROW}\n"))
    for name, payload in CASES.items():
        assert to_json(_check(payload)) != clean, (
            f"{name!r} produced the same report as a well-formed file"
        )


def test_the_status_line_explains_why_an_advisory_kept_it_unvalidated() -> None:
    report = _check(b"\xef\xbb\xbf" + f"{HEADER}\n{GOOD_ROW}\n".encode())
    text = to_text(report)
    assert "NOT reported as clean" in text
    assert "advisory" in text


def test_a_finding_names_the_spreadsheet_cell() -> None:
    report = _check(f"{HEADER}\n101,2025,1,77,B,A1,925190,1200,4500000,1\n")
    finding = next(f for f in report.findings if f.rule_id == "QP013")
    assert finding.cell == "D2"
    assert "cell D2" in to_text(report)


def test_advisories_appear_in_the_json_payload() -> None:
    report = _check(b"\xef\xbb\xbf" + f"{HEADER}\n{GOOD_ROW}\n".encode())
    payload = to_json(report)
    assert '"advisories"' in payload
    assert "ADV-BOM" in payload
    assert '"advisory": 1' in payload


def test_a_profile_without_the_column_is_unaffected() -> None:
    """The 1306B profile has no CustomerType, so nothing here may assume one."""
    header = ",".join(PROFILE_1306B.header)
    report = _check(f"{header}\n=1,2025,1,SCE,Other,34,1,1,1\n", PROFILE_1306B)
    assert "ADV-FORMULA-CELL" in _advisory_codes(report)
    assert "QP014" not in _rule_ids(report)
