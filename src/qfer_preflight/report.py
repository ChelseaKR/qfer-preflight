"""Rendering of reports for humans and for machines.

The JSON rendering is canonical: keys sorted, no trailing whitespace, a single
trailing newline. Two runs over the same bytes with the same tool version
produce byte-identical JSON, which is what lets a caller hash the output and
compare runs.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

from .model import Finding, Report, Severity, severity_rank
from .rules import RuleSpec

_SEVERITY_LABEL = {
    Severity.ERROR: "ERROR",
    Severity.WARNING: "WARN",
    Severity.INFO: "INFO",
    Severity.UNVALIDATED: "UNVAL",
}

# How many distinct findings this rendering prints for one rule and column.
# Identical findings are already merged into one line before they get here, so
# reaching this means that many genuinely different messages, most often the
# same mistake made with a different value in every row. The text stops
# listing them and says how many it stopped at; the JSON rendering carries
# every one. See ADR 0006.
_LINES_PER_RULE_AND_COLUMN = 10


def to_json(report: Report) -> str:
    """Canonical JSON rendering, ending in a single newline."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


def _location(row: int | None, column: str | None, cell: str | None = None) -> str:
    if row is None:
        return "file"
    if column is None:
        return f"row {row}"
    if cell:
        return f"cell {cell} (row {row}, {column})"
    return f"row {row}, {column}"


def _rows_phrase(rows: Sequence[int]) -> str:
    return ", ".join(f"{row:,}" for row in rows)


def _lines_phrase(count: int) -> str:
    return f"{count:,} line" if count == 1 else f"{count:,} lines"


def _repeat_note(finding: Finding) -> str:
    """What a merged finding stands for, in one sentence.

    Never silent about the merge: a line that speaks for more than one row
    always says how many, and names as many of them as it kept.
    """
    if finding.occurrences == 1:
        return ""
    listed = _rows_phrase(finding.example_rows)
    if finding.occurrences <= len(finding.example_rows):
        return f"The same finding appears on {finding.occurrences:,} rows: rows {listed}."
    span = ""
    if finding.example_rows and finding.last_row is not None:
        span = f", from row {finding.example_rows[0]:,} to row {finding.last_row:,}"
    return (
        f"The same finding appears on {finding.occurrences:,} rows{span}. "
        f"First rows: {listed}. The rest are counted, not listed."
    )


def _findings_section(report: Report) -> list[str]:
    """The findings list, plus a statement of everything it collapsed."""
    ordered = sorted(
        report.checked_findings(),
        key=lambda f: (
            severity_rank(f.severity.value),
            f.row if f.row is not None else -1,
            f.rule_id,
        ),
    )
    if not ordered:
        return ["Findings: none", ""]

    body: list[str] = []
    shown = 0
    seen: dict[tuple[str, str], int] = {}
    withheld: dict[tuple[str, str], list[int]] = {}
    for finding in ordered:
        key = (finding.rule_id, finding.column or "")
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > _LINES_PER_RULE_AND_COLUMN:
            tally = withheld.setdefault(key, [0, 0])
            tally[0] += 1
            tally[1] += finding.occurrences
            continue
        shown += 1
        label = _SEVERITY_LABEL[finding.severity]
        where = _location(finding.row, finding.column, finding.cell)
        body.append(f"  [{label}] {finding.rule_id}  {where}: {finding.message}")
        note = _repeat_note(finding)
        if note:
            body.append(f"      {note}")

    body.extend(_withheld_lines(withheld))
    body.extend(_collapse_note(report, len(ordered)))
    body.append("")
    return [_findings_heading(len(ordered), report.finding_count, shown), *body]


def _findings_heading(line_count: int, total: int, shown: int) -> str:
    """Say up front how many lines there are, and how many of them are printed."""
    if total == line_count and shown == line_count:
        return f"Findings ({line_count}):"
    bits = [_lines_phrase(line_count)]
    if total != line_count:
        bits.append(f"standing for {total:,} findings")
    if shown != line_count:
        bits.append(f"{shown:,} listed below")
    return "Findings (" + ", ".join(bits) + "):"


def _withheld_lines(withheld: dict[tuple[str, str], list[int]]) -> list[str]:
    lines = []
    for (rule_id, column), (distinct, occurrences) in sorted(withheld.items()):
        where = f" in column {column}" if column else ""
        lines.append(
            f"  [MORE] {rule_id}  {distinct:,} further findings{where} are not "
            f"listed here, covering {occurrences:,} rows. Each has a different "
            f"message, so this text report stops at {_LINES_PER_RULE_AND_COLUMN} "
            "for one rule and column. Re-run with --format json for every one."
        )
    return lines


def _collapse_note(report: Report, line_count: int) -> list[str]:
    merged = report.merged_finding_count
    if not merged:
        return []
    return [
        f"  Collapsed: {merged:,} findings repeated a rule, a column and a message "
        f"already reported, and were merged into {_lines_phrase(line_count)}. Two "
        "findings merge only when all three are identical, so no message was "
        "rewritten and no distinct problem was hidden. Every line says how many "
        "rows it stands for."
    ]


def to_text(report: Report, rules_by_id: dict[str, object] | None = None) -> str:
    """Human readable rendering."""
    lines: list[str] = []
    lines.append(f"{report.tool} {report.tool_version}")
    lines.append(f"profile : {report.profile_id}  ({report.profile_title})")
    lines.append(f"input   : {report.input_name}")
    lines.append(f"sha256  : {report.input_sha256}")
    lines.append(f"rows    : {report.rows_read}")
    lines.append(f"status  : {report.status.value.upper()}")
    lines.append("")
    lines.extend(_findings_section(report))

    if report.advisories:
        lines.append(f"Advisories ({len(report.advisories)}):")
        lines.append(
            "  These are not CEC rules and no published document calls them "
            "wrong. They are things the reader noticed, or had to do to the "
            "bytes, that a report with no findings would otherwise hide."
        )
        for advisory in report.checked_advisories():
            where = _location(advisory.row, advisory.column)
            lines.append(f"  [ADVIS] {advisory.code}  {where}: {advisory.message}")
        lines.append("")

    if report.rules_not_evaluated:
        lines.append(f"Not evaluated ({len(report.rules_not_evaluated)}):")
        for item in report.rules_not_evaluated:
            lines.append(f"  [UNVAL] {item.rule_id}: {item.reason}")
        lines.append("")

    lines.append(
        f"Rules evaluated: {len(report.rules_evaluated)}"
        f" | not evaluated: {len(report.rules_not_evaluated)}"
        f" | advisories: {len(report.advisories)}"
    )
    if report.status.value == "unvalidated":
        reasons = []
        if report.rules_not_evaluated:
            reasons.append("one or more rules were never applied")
        if report.advisories:
            reasons.append("the reader raised an advisory no published rule covers")
        lines.append(
            "This submission is NOT reported as clean: "
            + " and ".join(reasons)
            + ", so parts of it are simply unchecked."
        )
    return "\n".join(lines) + "\n"


def rules_to_text(rules: Iterable[object]) -> str:
    """Render the rule registry with its citations."""
    lines: list[str] = []
    for rule in rules:
        status = "implemented" if rule.implemented else "NOT IMPLEMENTED"  # type: ignore[attr-defined]
        lines.append(f"{rule.id}  [{rule.severity.value}] [{status}]")  # type: ignore[attr-defined]
        lines.append(f"  {rule.title}")  # type: ignore[attr-defined]
        lines.append(f"  cites: {rule.citation.render()}")  # type: ignore[attr-defined]
        if rule.quote:  # type: ignore[attr-defined]
            lines.append(f'  quote: "{rule.quote}"')  # type: ignore[attr-defined]
        if rule.unimplemented_reason:  # type: ignore[attr-defined]
            lines.append(f"  not evaluated because: {rule.unimplemented_reason}")  # type: ignore[attr-defined]
        lines.append("")
    return "\n".join(lines)


def rules_to_json(rules: Iterable[object]) -> str:
    payload = [rule.to_dict() for rule in rules]  # type: ignore[attr-defined]
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def specs_summary(specs: Iterable[RuleSpec]) -> tuple[int, int]:
    """Return (implemented, registered-but-unimplemented) counts."""
    specs = list(specs)
    implemented = sum(1 for s in specs if s.implemented)
    return implemented, len(specs) - implemented
