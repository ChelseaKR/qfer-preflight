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
#
# The minor revision is not carried in the payload and never has been. A report
# states the major version it conforms to, and a reader who wants to know which
# additive fields a given major version has grown reads `minorVersion` in
# docs/schemas/report-v1.schema.json, where every minor revision is recorded.
# Adding a `schema_minor` field to the report would itself be the kind of change
# it exists to announce, so the number lives with the schema rather than beside
# it. `tests/test_report_schema.py` pins the literal.
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


# What a ledger entry counts, one unit at a time. A row rule is offered data
# rows, the header rule is offered the one header row, and a rule about the
# submission as an object is offered the file. Naming the unit is not
# decoration: without it a reader cannot tell "judged 1 of 1 file" from
# "judged 1 of 400,000 rows", and the first would look like a rule that had
# almost stopped running.
LEDGER_SUBJECTS: tuple[str, ...] = ("file", "header", "row")

# Why a rule judged nothing. The closed vocabulary exists because the number
# zero is exactly what this project refuses to publish on its own: a rule that
# judged no rows and a rule that was never asked to look are different facts,
# and a bare 0 is read as the second, or as nothing at all.
LEDGER_ZERO_REASONS: dict[str, str] = {
    "no_applicable_rows": (
        "The rule ran and no row fell inside the applicability its own published "
        "text states, so it reached no verdict on this file."
    ),
    "blocked_by": (
        "An earlier rule left the cells unreadable, so this rule could not be "
        "applied. The rule that stopped it is named in blocked_by."
    ),
    "column_absent": (
        "This form's published template carries no column this rule reads, so "
        "the rule does not apply to the form at all."
    ),
}


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """How many rows one rule judged on one column of this file.

    This is a measurement of the run, not a rule. It carries no severity, it
    produces no finding, and it moves no verdict. What it does is answer the
    question `rules_evaluated` cannot: a rule can be listed there, correctly,
    having read every row and judged none of them.

    Four numbers, and they add up. `offered` is how many units the reader
    handed this rule, `judged` how many it reached a verdict on, `exempt` how
    many its own published applicability does not reach, and `blocked` how
    many an earlier rule left unreadable. `offered` is not derived at read
    time and then trusted: the constructor refuses an entry whose parts do not
    sum to it, because a ledger whose arithmetic does not close is a ledger
    that has quietly lost rows.

    `zero_reason` is present exactly when `judged` is zero, and never
    otherwise. That is the whole point of the type. A zero with a reason
    attached says which of three different things happened; a zero on its own
    says none of them, and reads as "fine".
    """

    rule_id: str
    column: str | None
    subject: str
    evaluated: bool
    offered: int
    judged: int
    exempt: int
    blocked: int
    zero_reason: str | None = None
    blocked_by: str | None = None

    def __post_init__(self) -> None:
        if self.subject not in LEDGER_SUBJECTS:
            raise ValueError(
                f"ledger entry for {self.rule_id} names subject {self.subject!r}, "
                f"which is not one of {', '.join(LEDGER_SUBJECTS)}. The unit a "
                "count is in has to be one a reader can look up"
            )
        for name, value in (
            ("offered", self.offered),
            ("judged", self.judged),
            ("exempt", self.exempt),
            ("blocked", self.blocked),
        ):
            if value < 0:
                raise ValueError(f"ledger entry for {self.rule_id} counts {value} {name}")
        if self.judged + self.exempt + self.blocked != self.offered:
            raise ValueError(
                f"ledger entry for {self.rule_id} was offered {self.offered} but "
                f"accounts for {self.judged + self.exempt + self.blocked} "
                "(judged plus exempt plus blocked). A ledger that does not close "
                "has lost rows somewhere, and a lost row reads as a checked one"
            )
        if (self.zero_reason is None) == (self.judged == 0):
            raise ValueError(
                f"ledger entry for {self.rule_id} judged {self.judged} rows and "
                f"gives zero_reason {self.zero_reason!r}. A reason is stated "
                "exactly when nothing was judged: without one the zero reads as "
                "a clean result, and with one beside a real count it reads as a "
                "contradiction"
            )
        if self.zero_reason is not None and self.zero_reason not in LEDGER_ZERO_REASONS:
            raise ValueError(
                f"ledger entry for {self.rule_id} gives zero_reason "
                f"{self.zero_reason!r}, which is not in the closed vocabulary "
                f"{', '.join(sorted(LEDGER_ZERO_REASONS))}"
            )
        names_blocker = self.blocked > 0 or self.zero_reason == "blocked_by"
        if names_blocker and self.blocked_by is None:
            raise ValueError(
                f"ledger entry for {self.rule_id} says rows were blocked but does "
                "not name the rule that blocked them, so the reader cannot go and "
                "look at it"
            )
        if not names_blocker and self.blocked_by is not None:
            raise ValueError(
                f"ledger entry for {self.rule_id} names blocker {self.blocked_by!r} "
                "while reporting nothing blocked"
            )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rule_id": self.rule_id,
            # Written even when it is null, unlike every other optional field
            # in this module. The ledger is a table and a reader walks it
            # column by column; a row that simply lacks the key would have to
            # be told apart from one whose rule reads no column, and `subject`
            # is the field that says which.
            "column": self.column,
            "subject": self.subject,
            "evaluated": self.evaluated,
            "offered": self.offered,
            "judged": self.judged,
            "exempt": self.exempt,
            "blocked": self.blocked,
        }
        if self.zero_reason is not None:
            payload["zero_reason"] = self.zero_reason
        if self.blocked_by is not None:
            payload["blocked_by"] = self.blocked_by
        return payload


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
    # What each rule actually read on this file. Empty on a report built by
    # hand; every report the engine produces carries one entry per rule and
    # column. See `LedgerEntry`.
    evaluation: list[LedgerEntry] = field(default_factory=list)

    def to_json(self) -> str:
        """This report as the published JSON, identical to the CLI's.

        `report`, `detect` and `api` all import `model`, so the rendering
        functions cannot be imported at module scope without a cycle. Importing
        inside the method is the cycle break, and it keeps the rendering in one
        place rather than giving the API its own copy that could drift from
        what `qfer-preflight check --format json` prints.
        """
        from .report import to_json

        return to_json(self)

    def to_text(self) -> str:
        """This report as the human-readable rendering, identical to the CLI's."""
        from .report import to_text

        return to_text(self)

    def to_sarif(self) -> str:
        """This report as SARIF 2.1.0, identical to the CLI's."""
        from .report import report_to_sarif

        return report_to_sarif(self)

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
            "evaluation": [
                entry.to_dict()
                for entry in sorted(self.evaluation, key=lambda e: (e.rule_id, e.column or ""))
            ],
        }


# Schema major version of the batch envelope produced when `check` is given
# more than one input. The compatibility policy is the one stated above
# REPORT_SCHEMA_VERSION, applied to the envelope rather than to a single
# report. Each embedded report conforms to the single-report schema of the
# same version.
BATCH_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class BatchEntry:
    """One input's outcome inside a batch run.

    A batch is not a super-report: findings never merge across inputs and no
    count in the envelope aggregates across them. An input that could not be
    processed at all appears with `problem` set and no report, because an
    unreadable file has nothing to validate and pretending otherwise would be
    exactly the silence this tool exists to refuse.
    """

    input_name: str
    report: Report | None = None
    problem: str | None = None

    def __post_init__(self) -> None:
        if (self.report is None) == (self.problem is None):
            raise ValueError(
                "a batch entry carries exactly one of a report or a problem; "
                "an entry with both is ambiguous and an entry with neither "
                "says nothing"
            )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"input_name": self.input_name}
        if self.report is not None:
            payload["outcome"] = "validated"
            payload["status"] = self.report.status.value
            payload["report"] = self.report.to_dict()
            return payload
        problem = self.problem
        if problem is None:  # pragma: no cover - excluded by __post_init__
            raise ValueError("a batch entry without a report must carry a problem")
        payload["outcome"] = "not-validated"
        payload["problem"] = problem
        return payload
