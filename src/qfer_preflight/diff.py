"""What changed between two runs over the same filing.

A filer runs `check`, edits the spreadsheet, exports again and re-runs. Two
reports later, the question is what changed, and the answer used to be a shell
pipeline or a careful read of two texts.

The posture is the one the rest of the tool holds. This says nothing the two
reports do not already say: it re-keys them and states which lines are the same
lines. It does not guess which edit caused a change, does not merge across
inputs, and does not aggregate -- the unit is one filing, two runs.

**What "the same finding" means.** A finding line is identified by its rule, its
column and its message text, which is exactly the identity ADR 0006 already uses
to decide that two findings may be merged. Rows are compared separately and
under that identity, so a filer who fixed row 4 and introduced the same problem
at row 900 is told the count and the rows moved, not that an old problem
vanished and a new one appeared. An advisory is identified by its code and
column; an unevaluated rule by its rule id.

**What it refuses.** Two reports about different profiles are not comparable and
neither are two written against different schema versions; a batch envelope is
not a report at all. Each is refused with the reason named, rather than diffed
into a number nobody should read. That is the same rule the validator applies to
a filing it cannot parse.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import REPORT_SCHEMA_VERSION, Severity

#: Status of one line in the comparison.
RESOLVED = "resolved"
NEW = "new"
UNCHANGED = "unchanged"
CHANGED = "changed"

_ORDER = (RESOLVED, NEW, CHANGED, UNCHANGED)


class NotComparable(Exception):
    """The two documents cannot be compared, with the reason in the message."""


def load_report(path: Path) -> dict[str, Any]:
    """One single-report JSON document, or a refusal saying why it is not one."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise NotComparable(f"{path}: cannot be read: {exc}") from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NotComparable(f"{path}: is not JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise NotComparable(f"{path}: is not a qfer-preflight report")
    if document.get("kind") == "qfer-preflight/batch" or "results" in document:
        raise NotComparable(
            f"{path}: is a batch envelope, not a single report. A batch is an "
            "outcome list over several filings and findings never merge across "
            "them, so there is no single pair of runs here to compare. Diff the "
            "reports for one input against each other."
        )
    for required in ("profile", "input", "findings", "schema_version"):
        if required not in document:
            raise NotComparable(f"{path}: is not a qfer-preflight report (no {required!r})")
    return document


def _finding_key(finding: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(finding.get("rule_id", "")),
        str(finding.get("column") or ""),
        str(finding.get("message", "")),
    )


def _rows_of(finding: dict[str, Any]) -> list[int]:
    """The rows this line stands for, as far as the report records them.

    A collapsed finding records its first few rows and its last, not all of
    them, so this is a sample and is treated as one: it is reported beside the
    occurrence count and never used to compute a difference of its own.
    """
    rows = [int(r) for r in finding.get("example_rows", []) if isinstance(r, int)]
    for field in ("row", "last_row"):
        value = finding.get(field)
        if isinstance(value, int) and value not in rows:
            rows.append(value)
    return sorted(rows)


def _occurrences(finding: dict[str, Any]) -> int:
    value = finding.get("occurrences", 1)
    return value if isinstance(value, int) and value >= 1 else 1


def _entry(status: str, key: tuple[str, ...], before: Any, after: Any) -> dict[str, Any]:
    return {"status": status, "key": list(key), "before": before, "after": after}


def _compare(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    key: Any,
    describe: Any,
) -> list[dict[str, Any]]:
    """Line-by-line comparison of two lists under one identity function."""
    left = {key(item): item for item in before}
    right = {key(item): item for item in after}
    entries: list[dict[str, Any]] = []
    for k in sorted(set(left) - set(right)):
        entries.append(_entry(RESOLVED, k, describe(left[k]), None))
    for k in sorted(set(right) - set(left)):
        entries.append(_entry(NEW, k, None, describe(right[k])))
    for k in sorted(set(left) & set(right)):
        a, b = describe(left[k]), describe(right[k])
        entries.append(_entry(UNCHANGED if a == b else CHANGED, k, a, b))
    return entries


def _describe_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": finding.get("severity"),
        "occurrences": _occurrences(finding),
        "rows": _rows_of(finding),
    }


def _describe_advisory(advisory: dict[str, Any]) -> dict[str, Any]:
    return {"occurrences": _occurrences(advisory), "message": advisory.get("message")}


def _describe_unevaluated(entry: dict[str, Any]) -> dict[str, Any]:
    return {"reason": entry.get("reason")}


def _incomparable(before: dict[str, Any], after: dict[str, Any]) -> str | None:
    """Why these two reports may not be compared, or None."""
    left, right = before["profile"], after["profile"]
    if left.get("id") != right.get("id"):
        return (
            f"the reports describe different profiles: {left.get('id')} and "
            f"{right.get('id')}. Two forms have different columns and different "
            "rules, so a finding in one has no counterpart in the other."
        )
    for document in (before, after):
        if document.get("schema_version") != REPORT_SCHEMA_VERSION:
            return (
                f"report schema version {document.get('schema_version')!r} is not "
                f"{REPORT_SCHEMA_VERSION}, which is the version this build reads. "
                "A field may have changed meaning between them."
            )
    return None


def diff_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two single-report documents about the same profile."""
    reason = _incomparable(before, after)
    if reason is not None:
        raise NotComparable(reason)

    findings = _compare(
        before.get("findings", []), after.get("findings", []), _finding_key, _describe_finding
    )
    advisories = _compare(
        before.get("advisories", []),
        after.get("advisories", []),
        lambda a: (str(a.get("code", "")), str(a.get("column") or "")),
        _describe_advisory,
    )
    unevaluated = _compare(
        before.get("rules_not_evaluated", []),
        after.get("rules_not_evaluated", []),
        lambda n: (str(n.get("rule_id", "")),),
        _describe_unevaluated,
    )
    return {
        "tool": "qfer-preflight",
        "profile": before["profile"],
        "before": {
            "tool_version": before.get("tool_version"),
            "input": before.get("input"),
            "status": before.get("status"),
        },
        "after": {
            "tool_version": after.get("tool_version"),
            "input": after.get("input"),
            "status": after.get("status"),
        },
        "findings": findings,
        "advisories": advisories,
        "rules_not_evaluated": unevaluated,
    }


def new_error_appeared(diff: dict[str, Any]) -> bool:
    """Whether any error-level finding is present after and was not before.

    A line whose occurrence count rose is not a new finding: it is the same
    published rule failing on the same column with the same message, and
    reporting it as new would tell a filer they had introduced a problem they
    already had.
    """
    return any(
        entry["status"] == NEW and (entry["after"] or {}).get("severity") == Severity.ERROR.value
        for entry in diff["findings"]
    )


def _rows_phrase(rows: list[int]) -> str:
    if not rows:
        return ""
    shown = ", ".join(str(r) for r in rows[:5])
    return f" rows {shown}{'…' if len(rows) > 5 else ''}"


def _finding_line(entry: dict[str, Any]) -> str:
    rule, column, message = entry["key"]
    where = f" [{column}]" if column else ""
    side = entry["after"] or entry["before"] or {}
    severity = side.get("severity", "")
    head = f"  {entry['status']:9} {rule}{where} ({severity}): {message}"
    if entry["status"] == CHANGED:
        before, after = entry["before"], entry["after"]
        if before["occurrences"] != after["occurrences"]:
            head += f"\n             count {before['occurrences']} -> {after['occurrences']}"
        if before["rows"] != after["rows"]:
            head += (
                f"\n             rows{_rows_phrase(before['rows'])} ->{_rows_phrase(after['rows'])}"
            )
    elif side.get("occurrences", 1) != 1:
        head += f"\n             {side['occurrences']} rows,{_rows_phrase(side['rows'])}"
    return head


def _section(title: str, entries: list[dict[str, Any]], render: Any) -> list[str]:
    if not entries:
        return []
    lines = [f"{title}:"]
    ordered = sorted(entries, key=lambda e: (_ORDER.index(e["status"]), e["key"]))
    lines.extend(render(entry) for entry in ordered)
    lines.append("")
    return lines


def _counts(entries: list[dict[str, Any]]) -> str:
    tally = {status: sum(1 for e in entries if e["status"] == status) for status in _ORDER}
    return ", ".join(f"{tally[s]} {s}" for s in _ORDER)


def to_text(diff: dict[str, Any]) -> str:
    """The comparison as a filer reads it.

    Every list the structure carries is rendered here. A section counted in the
    summary and printed nowhere would be a difference reported as nothing having
    happened, which is the failure this tool exists to refuse one level down.
    """
    before, after = diff["before"], diff["after"]
    lines = [
        f"qfer-preflight diff -- {diff['profile']['id']}",
        f"  before: {before['input']['name']} "
        f"(sha256 {before['input']['sha256'][:12]}, {before['status']}, "
        f"tool {before['tool_version']})",
        f"  after : {after['input']['name']} "
        f"(sha256 {after['input']['sha256'][:12]}, {after['status']}, "
        f"tool {after['tool_version']})",
        "",
    ]
    lines.extend(_section("Findings", diff["findings"], _finding_line))
    lines.extend(
        _section(
            "Advisories",
            diff["advisories"],
            lambda e: (
                f"  {e['status']:9} {e['key'][0]}" + (f" [{e['key'][1]}]" if e["key"][1] else "")
            ),
        )
    )
    lines.extend(
        _section(
            "Rules not evaluated",
            diff["rules_not_evaluated"],
            lambda e: (
                f"  {e['status']:9} {e['key'][0]}: "
                + str((e["after"] or e["before"] or {}).get("reason", ""))
            ),
        )
    )
    if not (diff["findings"] or diff["advisories"] or diff["rules_not_evaluated"]):
        lines.append("Neither run reported anything, so there is nothing to compare.")
        lines.append("")
    lines.append(f"findings: {_counts(diff['findings'])}")
    if diff["advisories"]:
        lines.append(f"advisories: {_counts(diff['advisories'])}")
    if diff["rules_not_evaluated"]:
        lines.append(f"not evaluated: {_counts(diff['rules_not_evaluated'])}")
    return "\n".join(lines) + "\n"


def to_json(diff: dict[str, Any]) -> str:
    return json.dumps(diff, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
