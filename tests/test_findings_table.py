"""The ungrouped findings table: one line per row and finding.

The property that matters here is not the formatting. It is that the table is
**ungrouped** -- and specifically that it is not, and cannot become, a table built by
expanding the report's merged findings. A merged `Finding` keeps only the first five
example rows, so a table derived from one would print five lines while its own header
claimed a line per row, and a filer would fix five rows out of four hundred thousand and
believe they were done. That is this project's own failure mode in a new costume, so the
first test below is the one that matters and it is written over a filing large enough
that merging genuinely happens.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from qfer_preflight import __version__
from qfer_preflight.engine import TOOL_NAME, FindingRow, validate_bytes
from qfer_preflight.findings_table import (
    FINDINGS_TABLE_COLUMNS,
    TableHeader,
    neutralise,
    render_findings_csv,
    render_findings_jsonl,
)
from qfer_preflight.profiles import Profile, get_profile

FIXTURES = Path(__file__).parent / "fixtures"

#: How many rows the repeated-finding fixture carries. Comfortably more than the five
#: `example_rows` a merged finding retains, so a table built from a merged group would
#: be visibly, countably short rather than short by one.
_REPEATED_ROWS = 40


def _profile() -> Profile:
    return get_profile("CEC-1306A-S1")


def _filing_with_a_repeated_error(rows: int = _REPEATED_ROWS) -> bytes:
    """`rows` rows, every one carrying the SAME bad county number.

    Identical rule, identical column, identical message -- which is exactly the
    condition under which the report merges them into one finding.
    """
    header = (FIXTURES / "1306a_s1_clean.csv").read_text(encoding="utf-8").splitlines()[0]
    body = "\n".join("1,2025,3,77,B,A,999999,1,2,3" for _ in range(rows))
    return f"{header}\n{body}\n".encode()


def _collect(data: bytes) -> list[FindingRow]:
    collected: list[FindingRow] = []
    validate_bytes(data, _profile(), "repeated.csv", collected.append)
    return collected


def test_a_repeated_finding_produces_one_line_per_row_not_one_per_group() -> None:
    """The whole point. The report merges; this table must not.

    If this ever reads 5, somebody has rebuilt the table from `Finding.example_rows`
    and the header's claim of "one line per row" has become false.
    """
    data = _filing_with_a_repeated_error()
    report = validate_bytes(data, _profile(), "repeated.csv")
    rows = _collect(data)

    county = [row for row in rows if row.rule_id == "QP013"]
    assert len(county) == _REPEATED_ROWS, (
        f"the table holds {len(county)} county findings for {_REPEATED_ROWS} bad rows"
    )

    merged = [f for f in report.findings if f.rule_id == "QP013"]
    assert len(merged) == 1, "the fixture no longer merges, so it no longer tests merging"
    assert len(merged[0].example_rows) < _REPEATED_ROWS, (
        "the report now keeps every row, so this test is no longer about the gap "
        "between the merged view and the ungrouped one"
    )

    assert sorted(row.row for row in county if row.row is not None) == list(
        range(2, _REPEATED_ROWS + 2)
    ), "the rows are not the actual rows; something reconstructed them"


def test_the_line_count_equals_the_reports_own_finding_count() -> None:
    """`Done when`: the table's line count equals `counts.findings` plus advisories."""
    data = (FIXTURES / "1306a_s1_dirty.csv").read_bytes()
    report = validate_bytes(data, _profile(), "1306a_s1_dirty.csv")
    rows = _collect(data)

    payload = json.loads(report.to_json())
    expected = payload["counts"]["findings"] + sum(
        advisory.get("occurrences", 1) for advisory in payload["advisories"]
    )
    assert len(rows) == expected


def test_an_empty_filing_is_one_line_not_zero_and_the_issue_expected_zero() -> None:
    """#56 says the table for an empty file has "zero lines". It has one, correctly.

    An empty file is not a filing with nothing wrong with it; it is a filing that
    could not be read, and `QP001` says so as an error. A zero-line table here would
    be the exact reading this project refuses -- "nothing found" standing in for
    "nothing could be checked". The issue's criterion is met in the sense that
    matters (the exit code is unchanged and the table states its status), and is
    wrong in its literal number, so this test pins the behaviour rather than the
    sentence.
    """
    rows = _collect(b"")
    assert [row.rule_id for row in rows] == ["QP001"]
    assert "empty" in rows[0].message


def test_a_clean_filing_gives_a_header_and_no_lines() -> None:
    """The genuine zero-line case, and the one a filer will meet."""
    rows = _collect((FIXTURES / "1306a_s1_clean.csv").read_bytes())
    assert rows == []

    header = TableHeader(
        tool=TOOL_NAME,
        tool_version=__version__,
        profile_id="CEC-1306A-S1",
        input_name="empty.csv",
        input_sha256=None,
        rows_read=None,
        status="unvalidated",
        lines=0,
    )
    rendered = render_findings_csv(header, rows)
    body = [line for line in rendered.splitlines() if not line.startswith("#")]
    assert body == [",".join(FINDINGS_TABLE_COLUMNS)], "zero lines, and the column row"


def test_a_zero_line_table_still_states_the_status() -> None:
    """An empty table for an unvalidated filing must not read as a clean bill.

    This is the `Findings: none` problem in a spreadsheet, and the header is the
    only thing standing between a filer and that reading.
    """
    header = TableHeader(
        tool=TOOL_NAME,
        tool_version=__version__,
        profile_id="CEC-1306A-S1",
        input_name="x.csv",
        input_sha256="abc",
        rows_read=3,
        status="unvalidated",
        lines=0,
    )
    rendered = render_findings_csv(header, [])
    assert "# status: UNVALIDATED" in rendered
    assert "THIS IS NOT THE REPORT" in rendered
    assert "never evaluated" in rendered, (
        "the header must point at the report, which is the only output that says "
        "which rules never ran"
    )


# ---------------------------------------------------------------------------
# Spreadsheet injection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("leader", ["=", "+", "-", "@"])
def test_every_formula_leader_is_neutralised(leader: str) -> None:
    assert neutralise(f"{leader}cmd|calc").startswith("'")


@pytest.mark.parametrize("value", [" =cmd", "\t+1", "   @SUM(A1)"])
def test_leading_whitespace_does_not_hide_a_formula(value: str) -> None:
    """Excel strips whitespace before deciding what it is looking at.

    A check that read index zero would pass `" =cmd"` straight through.
    """
    assert neutralise(value).startswith("'")


@pytest.mark.parametrize("value", ["2025", "CountyNumber", "", "A2", "error"])
def test_an_ordinary_value_is_left_exactly_alone(value: str) -> None:
    """The neutraliser must not corrupt the table it is protecting."""
    assert neutralise(value) == value


def test_the_rendered_table_has_no_cell_a_spreadsheet_would_execute() -> None:
    """`Done when`, read back with the CSV module rather than by eye.

    The rows here are hostile in every field on purpose. On the messages this tool
    emits today no field begins with a formula leader -- every message opens with a
    column name or a word -- so this is defence in depth rather than a live
    exploit. It is written over synthetic rows precisely because a fixture built
    from real findings would sit where the failure is impossible and would pass
    whether the neutraliser worked or not.
    """
    hostile = [
        FindingRow(
            row=2,
            column="=evil()",
            rule_id="+QP001",
            severity="-error",
            cell="@A1",
            message="=cmd|' /c calc'!A1",
        ),
        FindingRow(
            row=3, column=" =lead", rule_id="QP002", severity="error", cell="B3", message="-2+3"
        ),
    ]
    header = TableHeader(
        tool=TOOL_NAME,
        tool_version=__version__,
        profile_id="p",
        input_name="i",
        input_sha256="s",
        rows_read=3,
        status="fail",
        lines=len(hostile),
    )
    rendered = render_findings_csv(header, hostile)

    data = "\n".join(line for line in rendered.splitlines() if not line.startswith("#"))
    parsed = list(csv.reader(io.StringIO(data)))
    assert len(parsed) == len(hostile) + 1

    for record in parsed:
        for field in record:
            assert not field.lstrip().startswith(("=", "+", "-", "@")), (
                f"{field!r} would be executed by a spreadsheet"
            )


def test_the_jsonl_table_keeps_values_exactly_as_the_scan_saw_them() -> None:
    """JSONL is machine-read, so neutralising it would corrupt data for no gain."""
    hostile = [
        FindingRow(row=2, column="c", rule_id="QP001", severity="error", cell="A2", message="-2+3")
    ]
    header = TableHeader(
        tool=TOOL_NAME,
        tool_version=__version__,
        profile_id="p",
        input_name="i",
        input_sha256="s",
        rows_read=1,
        status="fail",
        lines=1,
    )
    lines = render_findings_jsonl(header, hostile).splitlines()
    assert json.loads(lines[0])["table"] == "findings"
    assert json.loads(lines[0])["status"] == "fail"
    assert json.loads(lines[1])["message"] == "-2+3"


# ---------------------------------------------------------------------------
# Ordering and the CLI surface
# ---------------------------------------------------------------------------


def test_file_level_findings_sort_before_row_findings() -> None:
    """A header the tool could not match makes every row finding under it provisional."""
    rows = [
        FindingRow(row=9, column="c", rule_id="QP010", severity="error", cell="A9", message="m"),
        FindingRow(
            row=None, column=None, rule_id="QP002", severity="error", cell=None, message="header"
        ),
        FindingRow(row=2, column="c", rule_id="QP010", severity="error", cell="A2", message="m"),
    ]
    header = TableHeader(
        tool=TOOL_NAME,
        tool_version=__version__,
        profile_id="p",
        input_name="i",
        input_sha256="s",
        rows_read=9,
        status="fail",
        lines=3,
    )
    body = [
        line for line in render_findings_csv(header, rows).splitlines() if not line.startswith("#")
    ][1:]
    assert body[0].startswith(","), "the file-level finding is not first"
    assert body[1].startswith("2,")
    assert body[2].startswith("9,")


def _cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "qfer_preflight", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_cli_writes_the_table_and_keeps_the_exit_code() -> None:
    """The output format is a rendering choice and must not change the verdict."""
    dirty = str(FIXTURES / "1306a_s1_dirty.csv")
    table = _cli(["check", dirty, "--format", "findings-csv"])
    report = _cli(["check", dirty])
    assert table.returncode == report.returncode == 1
    assert "THIS IS NOT THE REPORT" in table.stdout


def test_the_byte_order_mark_is_off_unless_asked_for() -> None:
    clean = str(FIXTURES / "1306a_s1_clean.csv")
    assert not _cli(["check", clean, "--format", "findings-csv"]).stdout.startswith("﻿")
    assert _cli(["check", clean, "--format", "findings-csv", "--findings-bom"]).stdout.startswith(
        "﻿"
    )


def test_a_batch_refuses_to_concatenate_tables_across_inputs() -> None:
    """One table per input, never one across inputs -- and it says why."""
    result = _cli(
        [
            "check",
            str(FIXTURES / "1306a_s1_clean.csv"),
            str(FIXTURES / "1306a_s1_dirty.csv"),
            "--format",
            "findings-csv",
        ]
    )
    assert result.returncode == 2
    assert "--findings-dir" in result.stderr


def test_a_batch_writes_one_table_per_input(tmp_path: Path) -> None:
    result = _cli(
        [
            "check",
            str(FIXTURES / "1306a_s1_clean.csv"),
            str(FIXTURES / "1306a_s1_dirty.csv"),
            "--format",
            "findings-csv",
            "--findings-dir",
            str(tmp_path),
        ]
    )
    written = sorted(p.name for p in tmp_path.glob("*.findings.csv"))
    assert written == ["1306a_s1_clean.findings.csv", "1306a_s1_dirty.findings.csv"]
    assert result.returncode == 1, "the dirty filing still fails the run"

    clean = (tmp_path / "1306a_s1_clean.findings.csv").read_text(encoding="utf-8")
    assert "# lines: 0" in clean
    assert "# status: UNVALIDATED" in clean, (
        "a zero-line table for an unvalidated filing must say so"
    )
