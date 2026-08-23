"""Core data model: citations, rules, findings and reports.

Two invariants hold everywhere in this package.

1. A rule cannot exist without a citation to a published source. The `Rule`
   constructor enforces it.
2. A rule that was not evaluated is never reported as passed. Every rule
   applicable to a profile ends up in exactly one of `rules_evaluated` or
   `rules_not_evaluated`, and anything in the latter drags the overall
   status away from `pass`.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Severity(enum.Enum):
    """How much a finding matters.

    UNVALIDATED is deliberately not an error. It means the tool declined to
    reach a conclusion. It is reported loudly so that silence is never
    mistaken for approval.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    UNVALIDATED = "unvalidated"

    def __str__(self) -> str:
        return self.value


# Ordering used only for stable, human friendly report sorting.
_SEVERITY_ORDER: dict[str, int] = {
    Severity.ERROR.value: 0,
    Severity.WARNING.value: 1,
    Severity.UNVALIDATED.value: 2,
    Severity.INFO.value: 3,
}


def severity_rank(severity: str) -> int:
    """Sort key for a severity string."""
    return _SEVERITY_ORDER.get(severity, 99)


# The major version of the JSON report's published schema. It appears in every
# report as `schema_version` and is validated against
# docs/schemas/report-v1.schema.json by tests/test_report_schema.py.
#
# Compatibility policy: adding an optional field or a new enum value is a
# minor change and does not move this number. Removing a field, renaming a
# field, changing a type, or tightening a constraint that existing reports
# satisfy is breaking: write the new major version of the schema file and bump
# this number in the same commit.
REPORT_SCHEMA_VERSION = 1


class Status(enum.Enum):
    """Overall verdict for one validated document."""

    PASS = "pass"  # nosec B105
    FAIL = "fail"
    UNVALIDATED = "unvalidated"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Citation:
    """A pointer to the published text a rule was derived from.

    `authority` is the regulation the form itself cites as its legal basis.
    `source` and `url` identify the document actually read. `locator` says
    where in that document the rule text sits.
    """

    source: str
    url: str
    locator: str
    authority: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("citation source must not be empty")
        if not self.url.strip():
            raise ValueError("citation url must not be empty")
        if not self.locator.strip():
            raise ValueError("citation locator must not be empty")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "url": self.url,
            "locator": self.locator,
        }
        if self.authority:
            payload["authority"] = self.authority
        return payload

    def render(self) -> str:
        parts = [f"{self.source}, {self.locator}"]
        if self.authority:
            parts.append(f"Authority: {self.authority}")
        parts.append(self.url)
        return " | ".join(parts)


@dataclass(frozen=True, slots=True)
class Rule:
    """A single check with a stable identifier and a citation.

    Rule identifiers are permanent. Once published, an identifier is never
    renumbered and never reused for a different check. A retired rule keeps
    its identifier and is marked retired rather than being deleted, so that a
    report produced by an older version can still be read.
    """

    id: str
    title: str
    severity: Severity
    citation: Citation
    quote: str | None = None
    implemented: bool = True
    unimplemented_reason: str | None = None
    retired: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("rule id must not be empty")
        if not self.title.strip():
            raise ValueError(f"rule {self.id} must have a title")
        if self.severity is Severity.UNVALIDATED and self.implemented:
            raise ValueError(
                f"rule {self.id} is implemented, so its severity must describe "
                "what a violation means, not the absence of evaluation"
            )
        if not self.implemented and not self.unimplemented_reason:
            raise ValueError(
                f"rule {self.id} is not implemented and must state why, so the "
                "report can explain what it did not check"
            )
        if self.implemented and self.unimplemented_reason:
            raise ValueError(f"rule {self.id} is implemented but carries an unimplemented reason")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.value,
            "implemented": self.implemented,
            "citation": self.citation.to_dict(),
        }
        if self.quote:
            payload["quote"] = self.quote
        if self.unimplemented_reason:
            payload["unimplemented_reason"] = self.unimplemented_reason
        if self.retired:
            payload["retired"] = True
        return payload


@dataclass(frozen=True, slots=True)
class Finding:
    """One observation about one document, possibly repeated across rows.

    `cell` is the spreadsheet reference for the offending value, for example
    "D2", so the filer can go straight to it instead of counting commas. It is
    the CSV record number and the column position, which line up with the
    spreadsheet unless a value contains a line break inside quotation marks.

    A finding that recurs identically is reported once rather than once per
    row. `occurrences` is how many rows produced it, `row` and `cell` point at
    the first of them, `example_rows` holds the first few, and `last_row` is
    the final one. Two findings are only ever merged when their rule, their
    column and their message text are all identical, so merging changes no
    wording and hides no distinct problem. See ADR 0006.
    """

    rule_id: str
    severity: Severity
    message: str
    row: int | None = None
    column: str | None = None
    cell: str | None = None
    occurrences: int = 1
    example_rows: tuple[int, ...] = ()
    last_row: int | None = None

    def __post_init__(self) -> None:
        if self.occurrences < 1:
            raise ValueError(
                f"finding {self.rule_id} claims {self.occurrences} occurrences; a "
                "finding that happened no times is not a finding"
            )
        if len(self.example_rows) > self.occurrences:
            raise ValueError(
                f"finding {self.rule_id} lists more example rows than it has "
                "occurrences, so its count understates what it stands for"
            )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.row is not None:
            payload["row"] = self.row
        if self.column is not None:
            payload["column"] = self.column
        if self.cell is not None:
            payload["cell"] = self.cell
        if self.occurrences != 1:
            payload["occurrences"] = self.occurrences
            payload["example_rows"] = list(self.example_rows)
            if self.last_row is not None:
                payload["last_row"] = self.last_row
        return payload


@dataclass(frozen=True, slots=True)
class NotEvaluated:
    """A rule that applied to this document but produced no verdict."""

    rule_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "reason": self.reason}


# The complete advisory code space. Nothing outside this table can be
# constructed, so a new advisory cannot be introduced by writing one line
# somewhere in the engine: it has to be registered here, next to the four
# others, where the question "should this have been a rule instead" is
# unavoidable. See ADR 0004 and ADR 0006.
ADVISORY_CODES: dict[str, str] = {
    "ADV-BOM": "The file begins with a UTF-8 byte order mark.",
    "ADV-LINE-ENDINGS": "The file does not settle on one ordinary line terminator.",
    "ADV-FORMULA-CELL": "A cell begins with a character a spreadsheet may evaluate.",
    "ADV-HIDDEN-CHARACTER": "A cell holds a character a spreadsheet does not show.",
    "ADV-REPEATED-HEADER": "A data row is an exact copy of the header row.",
}

# Every advisory has to say, in its own words, that the published record does
# not cover what it noticed. This is the phrase that says it. Requiring it is
# a blunt instrument and it is meant to be: an advisory is the one output
# channel with no citation behind it, so the sentence disclaiming published
# cover is the only thing standing between it and an uncited assertion.
_NO_PUBLISHED_COVER = "no published"


@dataclass(frozen=True, slots=True)
class Advisory:
    """Something the reader noticed that no published CEC rule addresses.

    Advisories are not findings and are deliberately kept in a separate list
    with a separate code space, `ADV-...` rather than `QP...`, so that nobody
    can mistake one for a cited rule. They exist because the alternative was
    worse: a file whose cells begin with "=", or whose header the reader
    silently repaired before matching it, previously produced an empty finding
    list that read exactly like a clean file.

    An advisory never carries a severity and never moves the status towards
    `pass`. It records a fact about the bytes, what the reader did about it,
    and that the published record does not address it. All three are enforced
    here rather than left to the author of the next advisory: there is no
    severity field, the code must be one of `ADVISORY_CODES`, and the message
    must contain the words that disclaim published cover. See ADR 0004.
    """

    code: str
    message: str
    row: int | None = None
    column: str | None = None
    occurrences: int = 1

    def __post_init__(self) -> None:
        if not self.code.startswith("ADV-"):
            raise ValueError(
                f"advisory code {self.code!r} must start with 'ADV-' so it cannot "
                "be mistaken for a rule identifier"
            )
        if self.code not in ADVISORY_CODES:
            raise ValueError(
                f"advisory code {self.code!r} is not registered in ADVISORY_CODES. "
                "Register it there, or write a rule with a citation instead"
            )
        if not self.message.strip():
            raise ValueError(f"advisory {self.code} must say what it noticed")
        if _NO_PUBLISHED_COVER not in self.message.casefold():
            raise ValueError(
                f"advisory {self.code} must say in its own text that the published "
                f"record does not cover what it noticed, using the words "
                f"{_NO_PUBLISHED_COVER!r}. An advisory carries no citation, so the "
                "message is the only place a reader learns that"
            )
        if self.occurrences < 1:
            raise ValueError(f"advisory {self.code} claims {self.occurrences} occurrences")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.row is not None:
            payload["row"] = self.row
        if self.column is not None:
            payload["column"] = self.column
        if self.occurrences != 1:
            payload["occurrences"] = self.occurrences
        return payload


@dataclass(slots=True)
class Report:
    """The complete result of validating one document."""

    tool: str
    tool_version: str
    profile_id: str
    profile_title: str
    input_name: str
    input_sha256: str
    findings: list[Finding] = field(default_factory=list)
    rules_evaluated: list[str] = field(default_factory=list)
    rules_not_evaluated: list[NotEvaluated] = field(default_factory=list)
    advisories: list[Advisory] = field(default_factory=list)
    rows_read: int = 0

    def checked_findings(self) -> list[Finding]:
        """The finding list, refusing anything that is not a `Finding`.

        The advisory channel has no citation behind it, so the one thing that
        must never happen is an advisory reaching the findings list, where a
        reader would take it for a cited rule. Nothing constructs a report
        that way today. This makes it impossible to start.
        """
        for item in self.findings:
            if not isinstance(item, Finding):
                raise TypeError(
                    f"{type(item).__name__} in the findings list. Only a Finding, "
                    "which carries a rule identifier and therefore a citation, may "
                    "be reported as one"
                )
        return self.findings

    def checked_advisories(self) -> list[Advisory]:
        """The advisory list, refusing anything that is not an `Advisory`."""
        for item in self.advisories:
            if not isinstance(item, Advisory):
                raise TypeError(f"{type(item).__name__} in the advisory list")
        return self.advisories

    def _severity_total(self, severity: Severity) -> int:
        return sum(f.occurrences for f in self.checked_findings() if f.severity is severity)

    @property
    def error_count(self) -> int:
        """How many rows carry an error, not how many lines report one."""
        return self._severity_total(Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return self._severity_total(Severity.WARNING)

    @property
    def finding_count(self) -> int:
        """Every occurrence of every finding, before any were merged."""
        return sum(f.occurrences for f in self.checked_findings())

    @property
    def merged_finding_count(self) -> int:
        """How many findings were folded into an identical one."""
        return self.finding_count - len(self.findings)

    @property
    def status(self) -> Status:
        """The verdict.

        A document is only `pass` when there were no errors AND every rule
        that applied to it was actually evaluated AND the reader raised no
        advisory. If anything went unevaluated, or the reader had to note
        something no published rule covers, the verdict is `unvalidated`. The
        tool does not have a way to say "clean" about a document it did not
        fully check.
        """
        if self.error_count:
            return Status.FAIL
        if self.rules_not_evaluated or self.advisories:
            return Status.UNVALIDATED
        return Status.PASS

    def to_dict(self) -> dict[str, Any]:
        ordered = sorted(
            self.checked_findings(),
            key=lambda f: (
                severity_rank(f.severity.value),
                f.row if f.row is not None else -1,
                f.rule_id,
                f.column or "",
                f.message,
            ),
        )
        return {
            "tool": self.tool,
            "tool_version": self.tool_version,
            "schema_version": REPORT_SCHEMA_VERSION,
            "profile": {"id": self.profile_id, "title": self.profile_title},
            "input": {"name": self.input_name, "sha256": self.input_sha256},
            "status": self.status.value,
            "counts": {
                "error": self.error_count,
                "warning": self.warning_count,
                "info": self._severity_total(Severity.INFO),
                "unvalidated": len(self.rules_not_evaluated),
                "advisory": len(self.advisories),
                "rows_read": self.rows_read,
                # "findings" counts occurrences and "finding_lines" counts the
                # entries below, which differ whenever a finding repeated.
                "findings": self.finding_count,
                "finding_lines": len(self.findings),
            },
            "collapsed": {
                "identical_findings_merged": self.merged_finding_count,
                "policy": (
                    "Findings that share a rule, a column and an identical message "
                    "are reported once, carrying the number of rows they cover, the "
                    "first few of those rows and the last. No finding is dropped and "
                    "no message is rewritten."
                ),
            },
            "findings": [f.to_dict() for f in ordered],
            "rules_evaluated": sorted(self.rules_evaluated),
            "rules_not_evaluated": [
                n.to_dict() for n in sorted(self.rules_not_evaluated, key=lambda n: n.rule_id)
            ],
            "advisories": [
                a.to_dict()
                for a in sorted(
                    self.checked_advisories(),
                    key=lambda a: (a.code, a.row if a.row is not None else -1, a.column or ""),
                )
            ],
        }
