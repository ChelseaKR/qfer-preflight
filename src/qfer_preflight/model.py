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
    """One observation about one document."""

    rule_id: str
    severity: Severity
    message: str
    row: int | None = None
    column: str | None = None

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
        return payload


@dataclass(frozen=True, slots=True)
class NotEvaluated:
    """A rule that applied to this document but produced no verdict."""

    rule_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "reason": self.reason}


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
    rows_read: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.WARNING)

    @property
    def status(self) -> Status:
        """The verdict.

        A document is only `pass` when there were no errors AND every rule
        that applied to it was actually evaluated. If anything went
        unevaluated, the verdict is `unvalidated`. The tool does not have a
        way to say "clean" about a document it did not fully check.
        """
        if self.error_count:
            return Status.FAIL
        if self.rules_not_evaluated:
            return Status.UNVALIDATED
        return Status.PASS

    def to_dict(self) -> dict[str, Any]:
        ordered = sorted(
            self.findings,
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
            "profile": {"id": self.profile_id, "title": self.profile_title},
            "input": {"name": self.input_name, "sha256": self.input_sha256},
            "status": self.status.value,
            "counts": {
                "error": self.error_count,
                "warning": self.warning_count,
                "info": sum(1 for f in self.findings if f.severity is Severity.INFO),
                "unvalidated": len(self.rules_not_evaluated),
                "rows_read": self.rows_read,
            },
            "findings": [f.to_dict() for f in ordered],
            "rules_evaluated": sorted(self.rules_evaluated),
            "rules_not_evaluated": [
                n.to_dict() for n in sorted(self.rules_not_evaluated, key=lambda n: n.rule_id)
            ],
        }
