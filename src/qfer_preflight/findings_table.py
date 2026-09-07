"""The ungrouped view of a run: one line per finding occurrence, for a spreadsheet.

The report merges. It has to: a county code that is wrong in all 400,000 rows is one
problem, and rendering it 400,000 times would bury every other problem in the filing.
ADR 0006 records that merge and points a reader who wants everything at the JSON.

A filer does not work in JSON. They work in the spreadsheet that produced the filing,
and what they need beside it is a table they can sort and filter: **one line per row and
finding**, so that fixing row 91,204 is a lookup rather than an inference.

## Why this is emitted during the scan and never derived from the report

A merged `Finding` keeps `occurrences`, the first row, `example_rows` -- **the first
five** -- and the last. Every row between the fifth and the last is not in it. A table
built by expanding merged findings would therefore print five lines, or seven, and its
header would say it was one line per row. A filer would sort it, fix what it listed,
re-run, and find the filing still rejected.

That is exactly the defect this tool exists to argue against, in the tool's own output:
a partial answer rendered as a complete one. So the ungrouped rows come from
`engine.FindingSink`, which is called once per occurrence as the single pass reaches it,
and this module never sees a `Finding` at all.

## Why every cell is neutralised

The tool already raises an advisory about formula-looking cells in a *filing*, because a
value beginning `=`, `+`, `-` or `@` is executed by Excel and Google Sheets when the file
is opened. That hazard does not stop applying because it is our file: a filer opens this
table in the same spreadsheet, and the messages in it quote the filing's own cell values.

So every field is neutralised on the way out, by prefixing an apostrophe -- the form both
Excel and Sheets read as "this is text". `-` is included, which costs a leading
apostrophe on negative numbers, and that is the right trade: a table of findings is read,
not summed, and the alternative is shipping the injection this tool warns filers about.

## Why the header is not optional

`Findings: none` reading as clean is the failure mode this whole tool is built against,
and an empty table is the same sentence in a different format. The header block therefore
carries the run's **status** alongside the counts, so a table with zero lines for a filing
that was never validated says so on its first line rather than looking like a clean bill.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from qfer_preflight.engine import FindingRow

__all__ = [
    "FINDINGS_TABLE_COLUMNS",
    "TableHeader",
    "neutralise",
    "render_findings_csv",
    "render_findings_jsonl",
]

#: The column order, fixed. A spreadsheet formula written against this table names
#: columns by position, so reordering them is a breaking change to somebody's sheet.
FINDINGS_TABLE_COLUMNS: tuple[str, ...] = (
    "row",
    "column",
    "rule_id",
    "severity",
    "cell",
    "message",
)

#: The characters a spreadsheet treats as the start of a formula.
_FORMULA_LEADERS = ("=", "+", "-", "@")

#: Prepended to a value that would otherwise be read as a formula. Both Excel and
#: Google Sheets treat a leading apostrophe as "the rest of this is text".
_TEXT_MARKER = "'"


def neutralise(value: str) -> str:
    """Return `value` in a form no spreadsheet will execute.

    Leading whitespace is considered, because a spreadsheet strips it before deciding
    what it is looking at: `" =cmd"` is a formula to Excel and would slip a check that
    only looked at index zero.
    """
    if value.lstrip().startswith(_FORMULA_LEADERS):
        return _TEXT_MARKER + value
    return value


@dataclass(frozen=True, slots=True)
class TableHeader:
    """What the table says about itself before its first data line.

    `status` is here on purpose. Without it a zero-line table for an UNVALIDATED
    filing is indistinguishable from a zero-line table for a clean one.
    """

    tool: str
    tool_version: str
    profile_id: str | None
    input_name: str | None
    input_sha256: str | None
    rows_read: int | None
    status: str
    lines: int

    def comment_lines(self) -> list[str]:
        """The `#`-prefixed preamble. Every value stated, absence stated as absence."""
        return [
            f"# {self.tool} {self.tool_version} findings table",
            "# THIS IS NOT THE REPORT. It is the ungrouped list of finding occurrences,",
            "# one line per row and finding, with nothing merged and nothing withheld.",
            "# Run `check --format text` or `--format json` for the report itself,",
            "# which is the only output that states which rules were never evaluated.",
            f"# profile: {self.profile_id or '(none: the filing was not matched)'}",
            f"# input: {self.input_name or '(none)'}",
            f"# input_sha256: {self.input_sha256 or '(not computed)'}",
            f"# rows_read: {'(not reached)' if self.rows_read is None else self.rows_read}",
            f"# status: {self.status.upper()}",
            f"# lines: {self.lines}",
        ]


def _cell(value: object) -> str:
    """One field, as text, with absence rendered as empty rather than as `None`."""
    if value is None:
        return ""
    return str(value)


def render_findings_csv(
    header: TableHeader,
    rows: Sequence[FindingRow],
    *,
    byte_order_mark: bool = False,
) -> str:
    """The table as CSV, every field neutralised, sorted by row then rule.

    `byte_order_mark` is off by default and exists for Excel, which reads a UTF-8
    file without one as the local code page and mangles anything non-ASCII.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for line in header.comment_lines():
        buffer.write(f"{line}\n")
    writer.writerow(FINDINGS_TABLE_COLUMNS)
    for entry in _sorted(rows):
        writer.writerow([neutralise(_cell(v)) for v in _fields(entry)])
    text = buffer.getvalue()
    return "﻿" + text if byte_order_mark else text


def render_findings_jsonl(header: TableHeader, rows: Sequence[FindingRow]) -> str:
    """The same table as JSON objects, one per line, header first.

    The header is a line of its own carrying `"table": "findings"`, so a consumer
    reading the stream can tell the preamble from the rows without counting.
    """
    lines = [
        json.dumps(
            {
                "table": "findings",
                "tool": header.tool,
                "tool_version": header.tool_version,
                "profile_id": header.profile_id,
                "input_name": header.input_name,
                "input_sha256": header.input_sha256,
                "rows_read": header.rows_read,
                "status": header.status,
                "lines": header.lines,
                "note": (
                    "not the report; the ungrouped finding occurrences only. "
                    "The report states which rules were never evaluated."
                ),
            },
            sort_keys=True,
        )
    ]
    # JSONL is machine-read, so the formula hazard does not apply and the values are
    # left exactly as the scan produced them.
    lines.extend(
        json.dumps(dict(zip(FINDINGS_TABLE_COLUMNS, _fields(entry), strict=True)), sort_keys=True)
        for entry in _sorted(rows)
    )
    return "\n".join(lines) + "\n"


def _fields(entry: FindingRow) -> tuple[object, ...]:
    return (entry.row, entry.column, entry.rule_id, entry.severity, entry.cell, entry.message)


def _sorted(rows: Iterable[FindingRow]) -> list[FindingRow]:
    """Row order, then rule, then column, then message.

    A row of `None` -- a file- or header-level finding, which happened before any row
    was read -- sorts first, because that is the order it happened in and it is also
    the order in which a filer has to fix things: a header the tool could not match
    makes every row finding beneath it provisional.
    """
    return sorted(
        rows,
        key=lambda e: (
            e.row is not None,
            e.row or 0,
            e.rule_id,
            e.column or "",
            e.message,
        ),
    )
