"""The validation engine.

The engine is fail-closed. Everything it cannot measure is reported as
unevaluated, never as a pass:

  * An empty file, a file that does not decode, or a file that does not parse
    as CSV produces an error and leaves every other rule unevaluated.
  * A header that does not match the published template produces an error and
    leaves every column-dependent rule unevaluated, because without a correct
    header the engine cannot tell which column holds which field.
  * A rule that is registered but not implemented is always listed as
    unevaluated, on every run, so its absence is visible in the output rather
    than being silently absent.

The consequence is deliberate: a document this tool has not fully checked can
never come back with the same verdict as one it has.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections.abc import Callable, Iterable, Sequence

from . import __version__
from .codes import (
    COUNTY_NAMES,
    COUNTY_NUMBERS,
    CUSTOMER_TYPES,
    CUSTOMER_TYPES_WORKSHOP_ONLY,
    GAS_RATE_CODES,
    PADDED_COUNTY_NUMBERS,
    RESIDENTIAL_CLASSIFICATION_CODES,
    VALID_UDC_VALUES,
    quarter_of_month,
)
from .model import Finding, NotEvaluated, Report
from .profiles import Profile
from .rules import RuleSpec, specs_for

TOOL_NAME = "qfer-preflight"

_FOUR_DIGIT_YEAR = re.compile(r"^\d{4}$")
_SMALL_INT = re.compile(r"^\d{1,2}$")
_NUMERIC_VALUE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

# The placeholders the instructions explicitly forbid in a numeric field.
_FORBIDDEN_PLACEHOLDERS = {"", "NULL", "-"}

# Rules that survive a header mismatch because they do not depend on knowing
# which column is which.
_HEADER_INDEPENDENT = frozenset({"QP001", "QP002", "QP004", "QP006"})


class ValidationInputError(Exception):
    """Raised when the caller asked for something impossible."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode(data: bytes) -> str | None:
    """Decode submission bytes, tolerating a UTF-8 byte order mark."""
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _describe_bad_characters(value: str) -> str:
    offenders = sorted({ch for ch in value if not (ch.isdigit() or ch in "+-.")})
    if not offenders:
        return "the value is not a plain number"
    rendered = ", ".join(repr(ch) for ch in offenders)
    return f"contains {rendered}"


class _Collector:
    """Accumulates findings and tracks which rules actually ran."""

    def __init__(self, specs: Sequence[RuleSpec]) -> None:
        self._specs = {spec.id: spec for spec in specs}
        self.findings: list[Finding] = []
        self._evaluated: set[str] = set()
        self._not_evaluated: dict[str, str] = {}

    def mark_evaluated(self, *rule_ids: str) -> None:
        for rule_id in rule_ids:
            if rule_id in self._specs and self._specs[rule_id].implemented:
                self._evaluated.add(rule_id)

    def mark_not_evaluated(self, rule_id: str, reason: str) -> None:
        if rule_id in self._specs:
            self._not_evaluated[rule_id] = reason
            self._evaluated.discard(rule_id)

    def add(
        self,
        rule_id: str,
        message: str,
        *,
        row: int | None = None,
        column: str | None = None,
    ) -> None:
        spec = self._specs[rule_id]
        self.findings.append(
            Finding(
                rule_id=rule_id,
                severity=spec.severity,
                message=message,
                row=row,
                column=column,
            )
        )

    def register_unimplemented(self) -> None:
        for spec in self._specs.values():
            if not spec.implemented:
                if spec.unimplemented_reason is None:  # pragma: no cover
                    raise ValueError(f"rule {spec.id} is unimplemented but states no reason")
                self._not_evaluated[spec.id] = spec.unimplemented_reason

    def block_all_except(self, keep: Iterable[str], reason: str) -> None:
        kept = set(keep)
        for spec in self._specs.values():
            if spec.id in kept or not spec.implemented:
                continue
            self.mark_not_evaluated(spec.id, reason)

    @property
    def evaluated(self) -> list[str]:
        return sorted(self._evaluated - set(self._not_evaluated))

    @property
    def not_evaluated(self) -> list[NotEvaluated]:
        return [
            NotEvaluated(rule_id=rid, reason=reason)
            for rid, reason in sorted(self._not_evaluated.items())
        ]


def _check_header(collector: _Collector, profile: Profile, header: Sequence[str]) -> bool:
    collector.mark_evaluated("QP002")
    actual = tuple(header)
    if actual == profile.header:
        return True
    expected_line = ",".join(profile.header)
    actual_line = ",".join(actual)
    collector.add(
        "QP002",
        (
            "Header row does not match the published template. "
            f"Expected: {expected_line}. Found: {actual_line}."
        ),
        row=1,
    )
    return False


def _check_numeric_cell(collector: _Collector, column: str, value: str, row_number: int) -> None:
    if value.strip().upper() in _FORBIDDEN_PLACEHOLDERS:
        shown = "an empty cell" if not value.strip() else repr(value.strip())
        collector.add(
            "QP019",
            (
                f"{column} holds {shown}. A zero must be written as 0 rather "
                'than left blank or filled with "NULL" or "-".'
            ),
            row=row_number,
            column=column,
        )
        return
    if not _NUMERIC_VALUE.fullmatch(value):
        collector.add(
            "QP020",
            (
                f"{column} value {value!r} {_describe_bad_characters(value)}. "
                "Numeric fields must not carry letters, spaces, comma "
                "separators or dollar signs."
            ),
            row=row_number,
            column=column,
        )


def _check_enum_cell(
    collector: _Collector,
    rule_id: str,
    column: str,
    value: str,
    allowed: Iterable[str],
    row_number: int,
    *,
    note: str = "",
) -> None:
    allowed_set = set(allowed)
    if value in allowed_set:
        return
    listing = ", ".join(sorted(allowed_set))
    message = f"{column} value {value!r} is not a published value. Allowed: {listing}."
    collector.add(rule_id, message + note, row=row_number, column=column)


def _check_county(collector: _Collector, column: str, value: str, row_number: int) -> None:
    if value in COUNTY_NUMBERS:
        return

    # A two-character zero-padded county, "01" to "09". The published table
    # writes these unpadded, but formatting rule 6 of the DSP workshop deck
    # tells filers how to preserve a leading zero on a County Number rather
    # than calling the value wrong, and no published source says it is an
    # error. So this is a warning, not a failure. See ADR 0003.
    unpadded = PADDED_COUNTY_NUMBERS.get(value)
    if unpadded is not None:
        collector.add(
            "QP024",
            (
                f"{column} value {value!r} is the zero-padded form of "
                f"{unpadded!r}, {COUNTY_NAMES[unpadded]}. The published county "
                f"table writes it {unpadded!r}; '00' for Unknown is the only "
                "county number the table writes with a leading zero. No "
                "published source calls the padded form an error, so this is "
                "reported as a warning rather than a failure."
            ),
            row=row_number,
            column=column,
        )
        return

    hint = ""
    stripped = value.lstrip("0")
    if stripped in COUNTY_NUMBERS and stripped != value:
        hint = (
            f" The published table writes {COUNTY_NAMES[stripped]} as "
            f"{stripped!r}; only Unknown is written '00'."
        )
    collector.add(
        "QP013",
        (
            f"{column} value {value!r} is not in the published county table "
            "(1 to 58, 99 for Multi, or '00' for Unknown)." + hint
        ),
        row=row_number,
        column=column,
    )


def _check_customer_type(collector: _Collector, column: str, value: str, row_number: int) -> None:
    if value in CUSTOMER_TYPES:
        return

    # The workshop deck lists a Customer Type the instruction PDF does not.
    # Two published CEC documents disagree, so the tool declines to call the
    # value an error and says why instead. See ADR 0003.
    restriction = CUSTOMER_TYPES_WORKSHOP_ONLY.get(value)
    if restriction is not None:
        collector.add(
            "QP025",
            (
                f"{column} value {value!r} is listed as valid by the DSP "
                f"workshop deck ({restriction}) but does not appear in the "
                "instructions, which list only "
                f"{', '.join(sorted(CUSTOMER_TYPES))}. The two published "
                "sources disagree, so this is reported for your attention "
                "rather than as an error. Confirm with the Commission that it "
                "still applies to you."
            ),
            row=row_number,
            column=column,
        )
        return

    published = sorted(set(CUSTOMER_TYPES) | set(CUSTOMER_TYPES_WORKSHOP_ONLY))
    collector.add(
        "QP014",
        (
            f"{column} value {value!r} is not a published value. Allowed: "
            f"{', '.join(sorted(CUSTOMER_TYPES))} per the instructions, and "
            f"{', '.join(sorted(CUSTOMER_TYPES_WORKSHOP_ONLY))} per the DSP "
            f"workshop deck, so {', '.join(published)} in total."
        ),
        row=row_number,
        column=column,
    )


def _check_naics(collector: _Collector, column: str, value: str, row_number: int) -> None:
    if len(value) != 6:
        collector.add(
            "QP017",
            (
                f"{column} value {value!r} is {len(value)} characters long. "
                "The code must be exactly 6 characters."
            ),
            row=row_number,
            column=column,
        )
    if value.strip().upper().startswith("RE") and value not in RESIDENTIAL_CLASSIFICATION_CODES:
        collector.add(
            "QP023",
            (
                f"{column} value {value!r} looks like a residential "
                "classification code but is not in the published "
                '"Residential CEC Custom Classification Codes" table.'
            ),
            row=row_number,
            column=column,
        )


def _check_integer_range(
    collector: _Collector,
    rule_id: str,
    column: str,
    value: str,
    low: int,
    high: int,
    row_number: int,
) -> int | None:
    if not _SMALL_INT.fullmatch(value) or not low <= int(value) <= high:
        collector.add(
            rule_id,
            f"{column} value {value!r} is not a whole number from {low} to {high}.",
            row=row_number,
            column=column,
        )
        return None
    return int(value)


def _check_year(collector: _Collector, column: str, value: str, row_number: int) -> str | None:
    if not _FOUR_DIGIT_YEAR.fullmatch(value):
        collector.add(
            "QP010",
            f"{column} value {value!r} is not a four-digit year.",
            row=row_number,
            column=column,
        )
        return None
    return value


def _check_identity_columns(
    collector: _Collector,
    profile: Profile,
    cell: Callable[[str], str],
    row_number: int,
    seen: dict[str, set[str]],
) -> None:
    """Company number, year, month and quarter."""
    column = profile.company_number_column
    if column and not cell(column).strip():
        collector.add("QP021", f"{column} is empty.", row=row_number, column=column)

    if profile.year_column:
        year = _check_year(collector, profile.year_column, cell(profile.year_column), row_number)
        if year:
            seen["years"].add(year)

    if profile.month_column:
        month = _check_integer_range(
            collector,
            "QP011",
            profile.month_column,
            cell(profile.month_column),
            1,
            12,
            row_number,
        )
        if month is not None:
            seen["months"].add(str(month))

    if profile.quarter_column:
        _check_integer_range(
            collector,
            "QP012",
            profile.quarter_column,
            cell(profile.quarter_column),
            1,
            4,
            row_number,
        )


def _check_codeset_columns(
    collector: _Collector,
    profile: Profile,
    cell: Callable[[str], str],
    row_number: int,
) -> None:
    """Columns whose values must come from a published code set."""
    if profile.county_column:
        _check_county(collector, profile.county_column, cell(profile.county_column), row_number)

    if profile.customer_type_column:
        _check_customer_type(
            collector,
            profile.customer_type_column,
            cell(profile.customer_type_column),
            row_number,
        )

    enum_checks: tuple[tuple[str | None, str, Iterable[str], str], ...] = (
        (
            profile.customer_group_column,
            "QP015",
            profile.customer_group_values,
            " The value must be spelled and capitalised exactly as published.",
        ),
        (profile.udc_column, "QP022", VALID_UDC_VALUES, ""),
        (profile.rate_code_column, "QP016", GAS_RATE_CODES, ""),
    )
    for column, rule_id, allowed, note in enum_checks:
        if column:
            _check_enum_cell(
                collector, rule_id, column, cell(column), allowed, row_number, note=note
            )

    if profile.naics_column:
        _check_naics(collector, profile.naics_column, cell(profile.naics_column), row_number)


def _row_checks(
    collector: _Collector,
    profile: Profile,
    row: Sequence[str],
    row_number: int,
    seen: dict[str, set[str]],
) -> None:
    """Run every column-dependent rule against one data row."""

    def cell(column: str) -> str:
        return row[profile.index_of(column)]

    _check_identity_columns(collector, profile, cell, row_number, seen)
    _check_codeset_columns(collector, profile, cell, row_number)
    for column in profile.numeric_columns:
        _check_numeric_cell(collector, column, cell(column), row_number)


def _cross_row_checks(collector: _Collector, seen: dict[str, set[str]]) -> None:
    months = {int(m) for m in seen["months"]}
    if months:
        quarters = {quarter_of_month(m) for m in months}
        if len(quarters) > 1:
            collector.add(
                "QP030",
                (
                    "Months in this submission span more than one calendar "
                    f"quarter (months {sorted(months)}, quarters "
                    f"{sorted(quarters)}). A quarterly report covers the three "
                    "months of a single quarter."
                ),
            )
    years = seen["years"]
    if len(years) > 1:
        collector.add(
            "QP031",
            (
                "Rows in this submission carry more than one reporting year "
                f"({', '.join(sorted(years))})."
            ),
        )


def _column_dependent_rule_ids(specs: Sequence[RuleSpec]) -> list[str]:
    return [spec.id for spec in specs if spec.implemented and spec.id not in _HEADER_INDEPENDENT]


def _parse_rows(text: str) -> list[list[str]] | None:
    try:
        return list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error:
        return None


def _scan_rows(
    collector: _Collector,
    profile: Profile,
    rows: Sequence[Sequence[str]],
    header_ok: bool,
) -> int:
    """Walk the data rows. Returns the number of non-blank data rows seen."""
    expected_width = len(profile.header)
    seen: dict[str, set[str]] = {"months": set(), "years": set()}
    data_rows = 0

    for offset, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            collector.add(
                "QP004",
                "Row is blank. Blank rows must be excluded from the submission.",
                row=offset,
            )
            continue
        data_rows += 1
        if not header_ok:
            continue
        if len(row) != expected_width:
            collector.add(
                "QP003",
                (f"Row has {len(row)} fields but the template defines {expected_width}."),
                row=offset,
            )
            continue
        _row_checks(collector, profile, row, offset, seen)

    if header_ok:
        _cross_row_checks(collector, seen)
    return data_rows


def validate_bytes(data: bytes, profile: Profile, input_name: str) -> Report:
    """Validate one submission held in memory."""
    specs = specs_for(profile)
    collector = _Collector(specs)
    collector.register_unimplemented()

    report = Report(
        tool=TOOL_NAME,
        tool_version=__version__,
        profile_id=profile.id,
        profile_title=profile.title,
        input_name=input_name,
        input_sha256=_sha256(data),
    )

    collector.mark_evaluated("QP001")
    text = _decode(data)
    if text is None or not text.strip():
        detail = "The file is empty." if text is not None else "The file is not valid UTF-8 text."
        collector.add("QP001", f"{detail} Nothing in it could be validated.")
        collector.block_all_except(
            ["QP001"],
            "The submission could not be read, so this rule was never applied.",
        )
        return _finish(report, collector, 0)

    rows = _parse_rows(text)
    if rows is None or not rows:
        collector.add("QP001", "The file could not be parsed as CSV.")
        collector.block_all_except(
            ["QP001"],
            "The submission could not be parsed, so this rule was never applied.",
        )
        return _finish(report, collector, 0)

    header_ok = _check_header(collector, profile, rows[0])
    if not header_ok:
        collector.block_all_except(
            _HEADER_INDEPENDENT,
            (
                "The header row does not match the published template, so the "
                "engine could not tell which column holds which field and did "
                "not apply this rule."
            ),
        )
    else:
        collector.mark_evaluated(*_column_dependent_rule_ids(specs))

    collector.mark_evaluated("QP003", "QP004", "QP006")
    data_rows = _scan_rows(collector, profile, rows, header_ok)
    if not header_ok:
        collector.mark_not_evaluated(
            "QP003",
            (
                "The header row does not match the published template, so the "
                "expected field count is unknown."
            ),
        )

    if data_rows == 0:
        collector.add(
            "QP006",
            "The file contains a header but no data rows, so nothing was validated.",
        )

    return _finish(report, collector, data_rows)


def _finish(report: Report, collector: _Collector, rows_read: int) -> Report:
    report.findings = collector.findings
    report.rules_evaluated = collector.evaluated
    report.rules_not_evaluated = collector.not_evaluated
    report.rows_read = rows_read
    return report


def validate_path(path: str, profile: Profile) -> Report:
    """Validate a submission on disk."""
    import os

    with open(path, "rb") as handle:
        data = handle.read()
    return validate_bytes(data, profile, os.path.basename(path))
