"""Rendering of reports for humans and for machines.

The JSON rendering is canonical: keys sorted, no trailing whitespace, a single
trailing newline. Two runs over the same bytes with the same tool version
produce byte-identical JSON, which is what lets a caller hash the output and
compare runs.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from .model import Report, Severity, severity_rank
from .rules import RuleSpec

_SEVERITY_LABEL = {
    Severity.ERROR: "ERROR",
    Severity.WARNING: "WARN",
    Severity.INFO: "INFO",
    Severity.UNVALIDATED: "UNVAL",
}


def to_json(report: Report) -> str:
    """Canonical JSON rendering, ending in a single newline."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


def _location(row: int | None, column: str | None) -> str:
    if row is None:
        return "file"
    if column is None:
        return f"row {row}"
    return f"row {row}, {column}"


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

    ordered = sorted(
        report.findings,
        key=lambda f: (
            severity_rank(f.severity.value),
            f.row if f.row is not None else -1,
            f.rule_id,
        ),
    )
    if ordered:
        lines.append(f"Findings ({len(ordered)}):")
        for finding in ordered:
            label = _SEVERITY_LABEL[finding.severity]
            where = _location(finding.row, finding.column)
            lines.append(f"  [{label}] {finding.rule_id}  {where}: {finding.message}")
        lines.append("")
    else:
        lines.append("Findings: none")
        lines.append("")

    if report.rules_not_evaluated:
        lines.append(f"Not evaluated ({len(report.rules_not_evaluated)}):")
        for item in report.rules_not_evaluated:
            lines.append(f"  [UNVAL] {item.rule_id}: {item.reason}")
        lines.append("")

    lines.append(
        f"Rules evaluated: {len(report.rules_evaluated)}"
        f" | not evaluated: {len(report.rules_not_evaluated)}"
    )
    if report.status.value == "unvalidated":
        lines.append(
            "This submission is NOT reported as clean. One or more rules were "
            "never applied, so parts of it are simply unchecked."
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
