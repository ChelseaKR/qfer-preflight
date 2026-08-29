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
  * Anything the reader noticed but no published rule covers is recorded as an
    advisory, in its own list with its own `ADV-` code space. An advisory is
    never dressed up as a cited rule, and it is never silently dropped either.
    See ADR 0004.

The consequence is deliberate: a document this tool has not fully checked can
never come back with the same verdict as one it has.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import os
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field

from . import __version__
from .codes import (
    COUNTY_NAMES,
    COUNTY_NUMBERS,
    CUSTOM_CLASSIFICATION_CODES,
    CUSTOMER_TYPES,
    CUSTOMER_TYPES_WORKSHOP_ONLY,
    GAS_RATE_CODES,
    PADDED_COUNTY_NUMBERS,
    RESIDENTIAL_CLASSIFICATION_CODES,
    VALID_UDC_VALUES,
    quarter_of_month,
)
from .describe import (
    cell_note,
    character_name,
    column_letter,
    formula_lead,
    header_report,
    hidden_characters,
    show,
)
from .model import Advisory, Finding, NotEvaluated, Report, Severity
from .profiles import Profile
from .rules import RuleSpec, specs_for

TOOL_NAME = "qfer-preflight"

# Digit classes are spelled out rather than written "\d". Python's "\d" matches
# every Unicode decimal digit, so "\d{4}" accepts the fullwidth "2025" and
# "\d{1,2}" accepts the Arabic-Indic "5", both of which int() then happily
# converts. That let a Year and a Month that no portal would accept pass with
# no finding at all. See ADR 0004.
_FOUR_DIGIT_YEAR = re.compile(r"^[0-9]{4}$")
_SMALL_INT = re.compile(r"^[0-9]{1,2}$")
_NUMERIC_VALUE = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?$")
_COMPANY_NUMBER_DIGITS = re.compile(r"^[0-9]+$")

# The placeholders the instructions explicitly forbid in a numeric field.
_FORBIDDEN_PLACEHOLDERS = {"", "NULL", "-"}

# Rules that survive a header mismatch because they do not depend on knowing
# which column is which.
_HEADER_INDEPENDENT = frozenset({"QP001", "QP002", "QP004", "QP006"})

# At most this many advisories per code and column. Beyond it the reader keeps
# counting but stops listing, so a formula in every row of a 400,000 row file
# is one line with a count rather than 400,000 lines.
_ADVISORY_EXAMPLES = 5

# How many example rows a merged finding names. Unlike the advisory cap above
# this discards nothing: the count, the first rows and the last row are all
# kept, and only rows in the middle of a run of identical findings go unnamed.
_FINDING_EXAMPLES = 5

# Advisories about the file as an object rather than about anything inside it.
# These stay true whether or not the file went on to parse, so they survive a
# parse failure that throws every finding away. See ADR 0006.
FILE_LEVEL_ADVISORY_CODES = frozenset({"ADV-BOM", "ADV-LINE-ENDINGS"})

_UTF8_BOM = b"\xef\xbb\xbf"

# How many bytes one pass of the reader takes at a time. Peak memory for a
# path validation is bounded by this, the longest single row, and the findings
# themselves; it does not grow with the size of the filing. Tests shrink it to
# force chunk boundaries through multibyte characters, quoted fields and
# carriage returns that straddle two reads.
_CHUNK_BYTES = 1 << 20


class ValidationInputError(Exception):
    """Raised when the caller asked for something impossible."""


class _CsvParseFailure(Exception):
    """Raised mid-scan when the CSV reader gives up part way through a file."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _describe_bad_characters(value: str) -> str:
    offenders = sorted({ch for ch in value if not (ch.isdigit() or ch in "+-.")})
    if not offenders:
        return "is not a plain number"
    rendered = ", ".join(character_name(ch) for ch in offenders)
    return f"contains {rendered}"


def _numeric_suggestion(value: str) -> str:
    """The same amount rewritten the way the instructions ask for it."""
    stripped = "".join(ch for ch in value if ch.isdigit() or ch in "+-.")
    if not _NUMERIC_VALUE.fullmatch(stripped):
        return ""
    return f" Written the way the instructions ask, this value is {stripped}."


@dataclass(slots=True)
class _FindingGroup:
    """One finding and every row that produced exactly the same one.

    Grouping happens here, as the findings are gathered, rather than in the
    renderer. A file with a bad county in all 400,000 rows would otherwise
    build 400,000 objects each holding the same three hundred character
    message before anything got the chance to summarise them.
    """

    rule_id: str
    severity: Severity
    message: str
    row: int | None
    column: str | None
    cell: str | None
    occurrences: int = 1
    example_rows: list[int] = field(default_factory=list)
    last_row: int | None = None

    def record(self, row: int | None) -> None:
        self.occurrences += 1
        if row is None:
            return
        self.last_row = row
        if len(self.example_rows) < _FINDING_EXAMPLES:
            self.example_rows.append(row)

    def to_finding(self) -> Finding:
        repeated = self.occurrences > 1
        return Finding(
            rule_id=self.rule_id,
            severity=self.severity,
            message=self.message,
            row=self.row,
            column=self.column,
            cell=self.cell,
            occurrences=self.occurrences,
            example_rows=tuple(self.example_rows) if repeated else (),
            last_row=self.last_row if repeated else None,
        )


class _Collector:
    """Accumulates findings and tracks which rules actually ran."""

    def __init__(self, specs: Sequence[RuleSpec], profile: Profile | None = None) -> None:
        self._specs = {spec.id: spec for spec in specs}
        self._profile = profile
        # Keyed by rule, column and the message text, which is what makes two
        # findings the same finding. Insertion order is first-seen order.
        self._groups: dict[tuple[str, str, str], _FindingGroup] = {}
        # Only the row currently being checked. `has_finding_at` is asked about
        # that row and no other, so keeping the whole file's worth would cost
        # memory proportional to the findings for no gain.
        self._cells_row: int | None = None
        self._cells: set[str] = set()
        self._evaluated: set[str] = set()
        self._not_evaluated: dict[str, str] = {}
        self._advisories: dict[tuple[str, str], Advisory] = {}
        self._advisory_counts: dict[tuple[str, str], int] = {}

    @property
    def findings(self) -> list[Finding]:
        return [group.to_finding() for group in self._groups.values()]

    def has_rule(self, rule_id: str) -> bool:
        """Whether this profile registers the rule, and it is implemented."""
        spec = self._specs.get(rule_id)
        return spec is not None and spec.implemented

    def mark_evaluated(self, *rule_ids: str) -> None:
        for rule_id in rule_ids:
            if rule_id in self._specs and self._specs[rule_id].implemented:
                self._evaluated.add(rule_id)

    def mark_not_evaluated(self, rule_id: str, reason: str) -> None:
        if rule_id in self._specs:
            self._not_evaluated[rule_id] = reason
            self._evaluated.discard(rule_id)

    def _cell_reference(self, row: int | None, column: str | None) -> str | None:
        if row is None or column is None or self._profile is None:
            return None
        try:
            index = self._profile.index_of(column)
        except ValueError:  # pragma: no cover
            return None
        return f"{column_letter(index)}{row}"

    def add(
        self,
        rule_id: str,
        message: str,
        *,
        row: int | None = None,
        column: str | None = None,
    ) -> None:
        """Report a finding, merging it with an identical one already held."""
        spec = self._specs[rule_id]
        if not spec.implemented:
            # A report cannot both assert a violation of a rule and list that
            # rule as never applied. Registering a rule as unimplemented is a
            # statement that no deterministic test for it exists, so a finding
            # citing one would be an assertion the registry contradicts.
            raise ValueError(
                f"rule {rule_id} is registered as unimplemented and reported as "
                "not evaluated, so it cannot also produce a finding"
            )
        key = (rule_id, column or "", message)
        group = self._groups.get(key)
        if group is None:
            self._groups[key] = _FindingGroup(
                rule_id=rule_id,
                severity=spec.severity,
                message=message,
                row=row,
                column=column,
                cell=self._cell_reference(row, column),
                example_rows=[] if row is None else [row],
                last_row=row,
            )
        else:
            group.record(row)
        self._note_cell(row, column)

    def _note_cell(self, row: int | None, column: str | None) -> None:
        if row is None or column is None:
            return
        if row != self._cells_row:
            self._cells_row = row
            self._cells = set()
        self._cells.add(column)

    def advise(
        self,
        code: str,
        message: str,
        *,
        row: int | None = None,
        column: str | None = None,
    ) -> None:
        """Record something no published rule covers, aggregated per column."""
        key = (code, column or "")
        self._advisory_counts[key] = self._advisory_counts.get(key, 0) + 1
        if self._advisory_counts[key] > _ADVISORY_EXAMPLES:
            return
        self._advisories[(code, f"{column or ''}#{self._advisory_counts[key]}")] = Advisory(
            code=code, message=message, row=row, column=column
        )

    def has_finding_at(self, row: int, column: str) -> bool:
        """Whether a cited rule has already spoken about this exact cell.

        Only ever asked about the row being checked, which is why only that
        row's cells are kept.
        """
        return row == self._cells_row and column in self._cells

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
    def registered(self) -> frozenset[str]:
        """Every rule this profile applies, implemented or not.

        The partition `_refuse_contradictions` enforces is over this set: each
        of these has to end up in exactly one of the two output lists.
        """
        return frozenset(self._specs)

    @property
    def evaluated(self) -> list[str]:
        return sorted(self._evaluated - set(self._not_evaluated))

    @property
    def not_evaluated(self) -> list[NotEvaluated]:
        return [
            NotEvaluated(rule_id=rid, reason=reason)
            for rid, reason in sorted(self._not_evaluated.items())
        ]

    def file_observations(self) -> list[Advisory]:
        """Advisories about the file itself rather than about a row in it.

        A byte order mark is in the bytes whether or not the CSV reader got to
        the end, so these are the observations that survive a parse failure.
        """
        return [
            advisory
            for advisory in self._advisories.values()
            if advisory.code in FILE_LEVEL_ADVISORY_CODES
            and advisory.row is None
            and advisory.column is None
        ]

    def readvise(self, advisories: Iterable[Advisory]) -> None:
        """Re-raise advisories carried over from an abandoned collector.

        Deliberately routed back through `advise` rather than copied into the
        dictionary, so that every advisory in every report has passed the same
        construction checks exactly once.
        """
        for advisory in advisories:
            self.advise(advisory.code, advisory.message)

    @property
    def advisories(self) -> list[Advisory]:
        """Every advisory, with a tail entry wherever the listing was capped."""
        out = list(self._advisories.values())
        for (code, column), total in sorted(self._advisory_counts.items()):
            if total <= _ADVISORY_EXAMPLES:
                continue
            where = f" in column {column}" if column else ""
            out.append(
                Advisory(
                    code=code,
                    message=(
                        f"{total} cells{where} raised this advisory. The first "
                        f"{_ADVISORY_EXAMPLES} are listed above; the rest are counted "
                        "only. As with every advisory, no published CEC document "
                        "addresses any of them."
                    ),
                    column=column or None,
                    occurrences=total,
                )
            )
        return out


# ---------------------------------------------------------------------------
# Whole-file reading, one bounded chunk at a time
# ---------------------------------------------------------------------------
#
# The reader walks the submission once, in chunks of _CHUNK_BYTES, and keeps
# only what a report needs: the hash, whether a byte order mark led the file,
# how many of each line ending it contains, whether anything non-whitespace
# was ever decoded, and whether a quoted field was still open at the end.
# Nothing proportional to the size of the filing is retained.
#
# Every fact collected here mirrors a definition that used to be written
# against the whole text, and the mirroring is checked two ways in the test
# suite: the adversarial corpus pins the observable behaviour end to end, and
# tests/test_streaming.py compares each scanner against its whole-text
# reference across deliberately tiny chunk sizes.


def _line_ending_advisory(collector: _Collector, crlf: int, lf: int, cr: int) -> None:
    """Note a file that does not settle on one ordinary line terminator.

    A bare carriage return counts on its own, not only in a mixture. It is the
    classic Mac line ending, this reader splits rows on it, and much other
    software does not, which means the same file can hold a different number
    of rows depending on what opens it.
    """
    kinds = {"CRLF": crlf, "LF (Unix)": lf, "CR (classic Mac)": cr}
    present = {name: count for name, count in kinds.items() if count}
    if len(present) < 2 and not cr:
        return
    listing = ", ".join(f"{count} {name}" for name, count in present.items())
    opening = "The file mixes line endings" if len(present) > 1 else "The file ends its lines"
    collector.advise(
        "ADV-LINE-ENDINGS",
        (
            f"{opening}: {listing}. This reader accepted them and read "
            "the rows below on that basis. Other software may split the rows "
            "differently, and a stray carriage return inside a value breaks one "
            "row into two. No published CEC document states which line ending "
            "to use. Re-save the file so every line ends the same way, with "
            "either CRLF or LF."
        ),
    )


def _bom_advisory(collector: _Collector, had_bom: bool) -> None:
    """Note a byte order mark, which is a fact about the file, not about a row.

    Raised before the file is decoded, so it is reported whatever happens
    next. The wording says only what is true on every path: the reader took
    the mark off the front before doing anything else. It cannot say the
    header check ignored it, because on the paths where the file never parsed
    there was no header check.
    """
    if not had_bom:
        return
    collector.advise(
        "ADV-BOM",
        (
            "The file begins with a UTF-8 byte order mark, the bytes EF BB BF. "
            "This reader removed it before reading anything else, so nothing "
            "reported below was affected by it. Software that does not remove "
            "it reads the first column name with an invisible character in "
            "front and will not match the template. No published CEC document "
            "addresses a byte order mark in a submission. If the header is "
            "rejected after this tool accepted it, re-save the file without "
            "the byte order mark."
        ),
    )


class _QuoteTrail:
    """Whether a quoted CSV field is still open, tracked while text flows past.

    This is the streaming mirror of `_unterminated_quote`, which remains in
    this module as the reference definition of truncation. The two agree on
    every input; `tests/test_streaming.py` walks thousands of generated
    strings through both to hold them together.

    `pending_close` carries the one case a per-chunk scan cannot settle on its
    own: the previous character was a quotation mark inside a quoted field,
    and whether it closes the field or merely escapes the next character
    depends on what comes after it, which may not arrive until the next chunk.
    """

    __slots__ = ("at_field_start", "in_quotes", "pending_close")

    def __init__(self) -> None:
        self.at_field_start = True
        self.in_quotes = False
        self.pending_close = False

    def feed(self, chunk: str) -> None:
        # Fast path: nothing here can open or close a field, so the state
        # moves only through the field separators at the tail.
        if not self.in_quotes and not self.pending_close and '"' not in chunk:
            if chunk:
                self.at_field_start = chunk[-1] in ",\r\n"
            return
        for char in chunk:
            self._step(char)

    def _step(self, char: str) -> None:
        if self.pending_close:
            self.pending_close = False
            if char == '"':
                return  # an escaped quotation mark; still inside the field
            self.in_quotes = False
            self.at_field_start = False
        if self.in_quotes:
            if char == '"':
                self.pending_close = True
            return
        if self.at_field_start and char == '"':
            self.in_quotes = True
            self.at_field_start = False
        else:
            self.at_field_start = char in ",\r\n"

    def finish(self) -> bool:
        """Resolve any pending close, then report whether a field stayed open."""
        if self.pending_close:
            # The reference implementation resolves a trailing quotation mark
            # the same way: with no next character, the field closes.
            self.pending_close = False
            self.in_quotes = False
            self.at_field_start = False
        return self.in_quotes


_BYTE_WHITESPACE = b" \t\n\r\x0b\f"

# Long enough to hold any trailing UTF-8 sequence the incremental decoder may
# still be buffering when the file stops mid-character, which is the only time
# the flush needs to name an exact byte it can no longer see.
_TAIL_BYTES = 16


class _StreamScan:
    """One pass over the raw bytes, keeping facts and discarding content."""

    __slots__ = (
        "_bom_settled",
        "_bom_shift",
        "_decoder",
        "_hash",
        "_prefix",
        "_prev_char",
        "_quote_trail",
        "_tail",
        "cr_total",
        "crlf",
        "decode_detail",
        "had_bom",
        "has_content",
        "lf_total",
        "size",
        "tail_has_nonspace",
    )

    def __init__(self) -> None:
        self._hash = hashlib.sha256()
        self._decoder = codecs.getincrementaldecoder("utf-8-sig")()
        self._quote_trail = _QuoteTrail()
        self._prefix = bytearray()
        self._tail = b""
        self._prev_char = ""
        self._bom_settled = False
        self._bom_shift = 0
        self.crlf = 0
        self.cr_total = 0
        self.lf_total = 0
        self.size = 0
        self.had_bom = False
        self.has_content = False
        self.tail_has_nonspace = False
        self.decode_detail: str | None = None

    def feed(self, raw: bytes) -> None:
        self._hash.update(raw)
        fed_before = self.size
        self.size += len(raw)
        if len(raw) >= _TAIL_BYTES:
            self._tail = raw[-_TAIL_BYTES:]
        else:
            self._tail = (self._tail + raw)[-_TAIL_BYTES:]
        self._bom_shift = self._settle_bom(raw)
        if self.decode_detail is not None:
            return
        try:
            text = self._decoder.decode(raw, final=False)
        except UnicodeDecodeError as exc:
            # Once the mark is stripped, the decoder's indices run from after
            # it. On the call that completes the mark, those bytes came out of
            # this chunk, so the shift is however many of them it supplied;
            # on every later call the mark sits entirely behind the offset
            # arithmetic and the shift is zero.
            shown_at = exc.start + self._bom_shift
            offending = raw[shown_at : shown_at + 1]
            self._record_decode_error(fed_before + shown_at, offending)
            return
        if text:
            self._absorb(text)

    def finish(self) -> None:
        """Close the stream: flush the decoder and settle the quote trail."""
        if self.decode_detail is None:
            try:
                text = self._decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                # A character cut in half by the end of the file. The
                # decoder's indices describe its buffered bytes, which are the
                # last exc.end bytes of the file.
                offset = self.size - exc.end
                byte = self._tail[-exc.end] if exc.end <= len(self._tail) else ord("?")
                self._record_decode_error(offset, bytes([byte]))
            else:
                if text:
                    self._absorb(text)

    def result(self) -> _Ingest:
        return _Ingest(
            sha256=self._hash.hexdigest(),
            had_bom=self.had_bom,
            size=self.size,
            decode_detail=self.decode_detail,
            has_content=self.has_content,
            tail_nonempty=self.had_bom and self.size > 3,
            tail_has_nonspace=self.tail_has_nonspace,
            crlf=self.crlf,
            lf=self.lf_total - self.crlf,
            cr=self.cr_total - self.crlf,
            truncated_quote=(self._quote_trail.finish() if self.decode_detail is None else False),
        )

    def _record_decode_error(self, offset: int, byte: bytes) -> None:
        shown = byte[0] if byte else ord("?")
        self.decode_detail = f"byte {offset} of the file is 0x{shown:02X}, which is not valid UTF-8"

    def _settle_bom(self, raw: bytes) -> int:
        """Decide whether the file leads with the mark.

        Returns how many bytes of this chunk the decoder consumed as part of
        the mark, which is the offset shift between its error indices and the
        physical file for this call alone.
        """
        if self._bom_settled:
            if self.had_bom and raw.translate(None, delete=_BYTE_WHITESPACE):
                self.tail_has_nonspace = True
            return 0
        needed = 3 - len(self._prefix)
        taken = raw[:needed]
        self._prefix.extend(taken)
        rest = raw[len(taken) :]
        if len(self._prefix) < 3:
            return 0  # still undecided; nothing has been stripped
        self._bom_settled = True
        self.had_bom = bytes(self._prefix) == _UTF8_BOM
        if not self.had_bom:
            return 0
        if rest.translate(None, delete=_BYTE_WHITESPACE):
            self.tail_has_nonspace = True
        return len(taken)

    def _absorb(self, text: str) -> None:
        if not self.has_content and text.strip():
            self.has_content = True
        self.lf_total += text.count("\n")
        self.cr_total += text.count("\r")
        self.crlf += text.count("\r\n")
        if self._prev_char == "\r" and text.startswith("\n"):
            self.crlf += 1
        self._prev_char = text[-1]
        self._quote_trail.feed(text)


@dataclass(frozen=True, slots=True)
class _Ingest:
    """What one pass over the file could say without holding the file."""

    sha256: str
    had_bom: bool
    size: int
    decode_detail: str | None
    has_content: bool
    tail_nonempty: bool
    tail_has_nonspace: bool
    crlf: int
    lf: int
    cr: int
    truncated_quote: bool


def _scan_stream(handle: io.BufferedIOBase) -> _Ingest:
    scan = _StreamScan()
    while True:
        block = handle.read(_CHUNK_BYTES)
        if not block:
            break
        scan.feed(block)
    scan.finish()
    return scan.result()


def _unterminated_quote(text: str) -> bool:
    """True when the file ends inside a quoted field, which means it is cut off.

    Python's CSV reader does not complain about this. It reaches the end of the
    input, hands back whatever it had accumulated, and the caller cannot tell a
    complete file from one that was truncated mid-value. This walks the text
    the way the reader does, tracking whether a quotation mark opened a field,
    and reports whether one was ever closed.
    """
    at_field_start = True
    in_quotes = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if in_quotes:
            if char == '"':
                if index + 1 < length and text[index + 1] == '"':
                    index += 2
                    continue
                in_quotes = False
                at_field_start = False
            index += 1
            continue
        if at_field_start and char == '"':
            in_quotes = True
            at_field_start = False
        else:
            at_field_start = char in ",\r\n"
        index += 1
    return in_quotes


def _formula_advisory(collector: _Collector, column: str, value: str, row_number: int) -> None:
    lead = formula_lead(value)
    if lead is None:
        return
    collector.advise(
        "ADV-FORMULA-CELL",
        (
            f"{column} on row {row_number} begins with {character_name(lead)}. "
            "Spreadsheet software reads a cell starting with that character as "
            "a formula and tries to evaluate it rather than storing the text, "
            "so the value that reaches the reviewer may not be the value you "
            "entered. No published CEC document addresses this. If the value "
            "is meant literally, remove the leading character."
        ),
        row=row_number,
        column=column,
    )


def _hidden_character_advisory(
    collector: _Collector, column: str, value: str, row_number: int
) -> None:
    """Flag an invisible character in a cell no cited rule has already judged.

    When a rule did fire on the same cell, its own message already names the
    character, so repeating it here would be noise and would also be untrue:
    the advisory says no published rule covers the value, and one just did.

    The wording is careful for the same reason. It used to say that no rule
    this tool implements constrains the column, which is false of, say, a
    NAICS Code that satisfied QP017 on length. What is true, and all that is
    claimed, is that nothing published addresses an invisible character and
    that no rule objected to this particular value.
    """
    if collector.has_finding_at(row_number, column):
        return
    hidden = [ch for ch in hidden_characters(value) if ch != " "]
    if not hidden:
        return
    names = ", ".join(character_name(ch) for ch in hidden)
    collector.advise(
        "ADV-HIDDEN-CHARACTER",
        (
            f"{column} on row {row_number} contains {names}, which a "
            "spreadsheet does not show. No published CEC document addresses an "
            "invisible character in a cell, and no rule this tool implements "
            "objected to this value, so it is reported here rather than as a "
            f"finding. The cell reads {show(value)}. Retype it if the "
            "character was not intended."
        ),
        row=row_number,
        column=column,
    )


# ---------------------------------------------------------------------------
# Rule checks
# ---------------------------------------------------------------------------


def _check_header(collector: _Collector, profile: Profile, header: Sequence[str]) -> bool:
    collector.mark_evaluated("QP002")
    if tuple(header) == profile.header:
        return True
    collector.add("QP002", header_report(profile.header, list(header)), row=1)
    return False


def _check_numeric_cell(collector: _Collector, column: str, value: str, row_number: int) -> None:
    if value.strip().upper() in _FORBIDDEN_PLACEHOLDERS:
        collector.add(
            "QP019",
            (
                f"{column} holds {show(value)}. Write a zero as 0. The "
                'instructions do not accept a blank cell, "NULL" or "-" in '
                "this column."
            ),
            row=row_number,
            column=column,
        )
        return
    if not _NUMERIC_VALUE.fullmatch(value):
        collector.add(
            "QP020",
            (
                f"{column} value {show(value)} {_describe_bad_characters(value)}. "
                "A numeric field takes digits only, with an optional leading "
                "minus sign and an optional decimal point. Remove any letters, "
                "spaces, comma separators and dollar signs."
                f"{_numeric_suggestion(value)}{cell_note(value)}"
            ),
            row=row_number,
            column=column,
        )


def _near_matches(value: str, allowed: Iterable[str]) -> list[str]:
    """Published values that differ from this one only in case or whitespace."""
    folded = value.strip().casefold()
    return sorted(candidate for candidate in allowed if candidate.casefold() == folded)


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
    message = f"{column} value {show(value)} is not a published value. Allowed: {listing}."
    near = _near_matches(value, allowed_set)
    if near:
        message += f" The published spelling is {', '.join(repr(n) for n in near)}."
    collector.add(rule_id, message + note + cell_note(value), row=row_number, column=column)


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
                f"{column} value {show(value)} is the zero-padded form of "
                f"{unpadded!r}, {COUNTY_NAMES[unpadded]}. The published county "
                f"table writes it {unpadded!r}; '00' for Unknown is the only "
                "county number the table writes with a leading zero. No "
                "published source calls the padded form an error, so this is "
                "reported as a warning rather than a failure. To match the "
                f"published table, write it as {unpadded!r}."
            ),
            row=row_number,
            column=column,
        )
        return

    collector.add(
        "QP013",
        (
            f"{column} value {show(value)} is not in the published county "
            "table. Use the county number where the customer consumed the "
            "energy: 1 to 58 for a California county, 99 for Multi, or '00' "
            f"for Unknown.{_county_hint(value)}{cell_note(value)}"
        ),
        row=row_number,
        column=column,
    )


def _county_hint(value: str) -> str:
    stripped = value.strip().lstrip("0")
    if stripped in COUNTY_NUMBERS and stripped != value:
        return (
            f" The published table writes {COUNTY_NAMES[stripped]} as "
            f"{stripped!r}; only Unknown is written '00'."
        )
    if value.strip().isdigit() and value.strip().isascii():
        number = int(value.strip())
        if number > 58 and number != 99:
            return f" There is no county {number}; the table stops at 58."
    return ""


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
                f"{column} value {show(value)} is listed as valid by the DSP "
                f"workshop deck ({restriction}) but does not appear in the "
                "instructions, which list only "
                f"{', '.join(sorted(CUSTOMER_TYPES))}. No revision of the "
                "instructions has ever listed it, and no published document "
                "says it is not accepted, so this is reported for your "
                "attention rather than as an error. Nothing needs changing on "
                "the strength of this note. If you are not filing for BART, "
                f"one of {', '.join(sorted(CUSTOMER_TYPES))} is the value you "
                "want; if you are, confirm with the Commission that the code "
                "still applies before you submit."
            ),
            row=row_number,
            column=column,
        )
        return

    legend = "; ".join(f"{code} = {name}" for code, name in sorted(CUSTOMER_TYPES.items()))
    collector.add(
        "QP014",
        (
            f"{column} value {show(value)} is not a published value. Use one "
            f"uppercase letter: {legend}. The DSP workshop deck adds "
            f"{', '.join(sorted(CUSTOMER_TYPES_WORKSHOP_ONLY))} "
            f"({', '.join(CUSTOMER_TYPES_WORKSHOP_ONLY.values())}), which the "
            f"instructions do not list.{cell_note(value)}"
        ),
        row=row_number,
        column=column,
    )


def _naics_hint(value: str) -> str:
    """Point at the published codes nearest to what was typed."""
    if not value.strip().upper().startswith("RE"):
        return ""
    prefix = value.strip().upper()[:4]
    near = sorted(code for code in RESIDENTIAL_CLASSIFICATION_CODES if code.startswith(prefix))
    if not near:
        opening = sorted(RESIDENTIAL_CLASSIFICATION_CODES)[:3]
        return f" The published table starts {', '.join(opening)} and so on."
    listing = ", ".join(f"{code} ({RESIDENTIAL_CLASSIFICATION_CODES[code]})" for code in near[:3])
    label = "code is" if len(near[:3]) == 1 else "codes are"
    return f" The nearest published {label} {listing}."


def _check_naics(collector: _Collector, column: str, value: str, row_number: int) -> None:
    if len(value) != 6:
        collector.add(
            "QP017",
            (
                f"{column} value {show(value)} is {len(value)} characters long. "
                "The code must be exactly 6 characters and should describe the "
                "primary activity at the location where the energy was "
                "consumed. This tool checks the length only; whether the code "
                "is on the Commission's list of valid NAICS codes is reported "
                f"as not evaluated under QP018.{cell_note(value)}"
            ),
            row=row_number,
            column=column,
        )
    if value.strip().upper().startswith("RE") and value not in RESIDENTIAL_CLASSIFICATION_CODES:
        custom = ", ".join(f"{code} ({name})" for code, name in CUSTOM_CLASSIFICATION_CODES.items())
        collector.add(
            "QP023",
            (
                f"{column} value {show(value)} looks like a residential "
                "classification code but is not in the published "
                '"Residential CEC Custom Classification Codes" table. Use a '
                "code from that table for a residential customer, or one of "
                f"the other CEC custom codes: {custom}."
                f"{_naics_hint(value)}{cell_note(value)}"
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
    example: str,
) -> int | None:
    if _SMALL_INT.fullmatch(value):
        number = int(value)
        if low <= number <= high:
            return number
        # A whole number, just not one of the published ones. Saying it "is not
        # a whole number" here would send the filer looking for a typo that is
        # not there.
        allowed = ", ".join(str(n) for n in range(low, high + 1))
        collector.add(
            rule_id,
            (
                f"{column} value {show(value)} is outside the published range. "
                f"The only values are {allowed}, for example {example}."
            ),
            row=row_number,
            column=column,
        )
        return None
    collector.add(
        rule_id,
        (
            f"{column} value {show(value)} is not a whole number from {low} to "
            f"{high}. Write it as a plain number with no leading zero and no "
            f"other characters, for example {example}.{cell_note(value)}"
        ),
        row=row_number,
        column=column,
    )
    return None


def _check_year(collector: _Collector, column: str, value: str, row_number: int) -> str | None:
    if not _FOUR_DIGIT_YEAR.fullmatch(value):
        collector.add(
            "QP010",
            (
                f"{column} value {show(value)} is not a four-digit year. Write "
                "the calendar year as four digits, for example 2025."
                f"{cell_note(value)}"
            ),
            row=row_number,
            column=column,
        )
        return None
    return value


def _check_company_number_form(
    collector: _Collector, column: str, value: str, row_number: int
) -> None:
    """The published form of a Company Number: digits alone.

    Every instruction document publishes the column as numeric data type,
    allowing text data type only so that a leading zero survives; both forms
    are digit strings on the page. CEC-1306B says outright that non-numeric
    characters must be removed. A blank cell is QP021's finding, not this
    one's.
    """
    stripped = value.strip()
    if not stripped:
        return
    if _COMPANY_NUMBER_DIGITS.fullmatch(stripped):
        return
    collector.add(
        "QP033",
        (
            f"{column} value {show(value)} {_describe_bad_characters(value)}. "
            "A company number is published as numeric data type, or as text "
            "only so a leading zero survives; either way it is written as "
            "digits alone. Remove any letters, spaces, dashes and separators."
            f"{cell_note(value)}"
        ),
        row=row_number,
        column=column,
    )


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
        collector.add(
            "QP021",
            (
                f"{column} is {show(cell(column))}. Every row needs the "
                "identification number CEC staff assigned to your company."
            ),
            row=row_number,
            column=column,
        )
    if column:
        _check_company_number_form(collector, column, cell(column), row_number)

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
            example="3 for March",
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
            example="2 for April to June",
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
            " Enter it spelled and capitalised exactly as published.",
        ),
        (
            profile.udc_column,
            "QP022",
            VALID_UDC_VALUES,
            " Enter the UDC exactly as spelled here, with no special characters such as '&'.",
        ),
        (profile.rate_code_column, "QP016", GAS_RATE_CODES, _rate_code_legend()),
    )
    for column, rule_id, allowed, note in enum_checks:
        if column:
            _check_enum_cell(
                collector, rule_id, column, cell(column), allowed, row_number, note=note
            )

    if profile.naics_column:
        _check_naics(collector, profile.naics_column, cell(profile.naics_column), row_number)


def _rate_code_legend() -> str:
    listing = "; ".join(f"{code} = {name}" for code, name in sorted(GAS_RATE_CODES.items()))
    return f" The published codes describe the type of gas delivery: {listing}."


def _repeated_header_row(
    collector: _Collector, profile: Profile, row: Sequence[str], row_number: int
) -> None:
    """Report a duplicated header row, as a rule or as an advisory.

    Which one depends on the form. Two of the five instruction documents,
    CEC-1306B and CEC-1308C, publish the sentence "Exclude any extra
    information, including extra headers, ..."; the other three publish the
    same sentence without the words "extra headers". So the same row is a
    cited error on two forms and an advisory on the other three, and QP007 is
    registered only where the text exists. See ADR 0007.
    """
    if tuple(row) != profile.header:
        return
    tail = (
        "The findings above treat it as data, which is why they complain that "
        "a Year reads 'Year'. Deleting this one row clears all of them. It "
        "most often appears when several quarters were pasted into one file."
    )
    if collector.has_rule("QP007"):
        collector.add(
            "QP007",
            (
                f"Row {row_number} is an exact copy of the header row, and the "
                "instructions for this form say to exclude extra headers from a "
                f"submission. {tail}"
            ),
            row=row_number,
        )
        return
    collector.advise(
        "ADV-REPEATED-HEADER",
        (
            f"Row {row_number} is an exact copy of the header row. The "
            "instructions for this form do not mention extra header rows, so "
            "no published text this tool can cite calls the row wrong and it "
            f"is reported here rather than as a finding. {tail}"
        ),
        row=row_number,
    )


def _row_advisories(
    collector: _Collector, profile: Profile, row: Sequence[str], row_number: int
) -> None:
    """Record what no published rule covers, so a quiet row is not a clean one."""
    _repeated_header_row(collector, profile, row, row_number)
    for index, column in enumerate(profile.header):
        value = row[index]
        # Almost every cell in a real filing is plain printable ASCII. Skipping
        # those without building a set per cell keeps a 400,000 row file quick.
        if value.isascii() and value.isprintable() and value[:1] not in "=@+-":
            continue
        _formula_advisory(collector, column, value, row_number)
        _hidden_character_advisory(collector, column, value, row_number)


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
    _row_advisories(collector, profile, row, row_number)


def _cross_row_checks(collector: _Collector, seen: dict[str, set[str]]) -> None:
    months = {int(m) for m in seen["months"]}
    if months:
        quarters = sorted({quarter_of_month(m) for m in months})
        if len(quarters) > 1:
            grouped = "; ".join(
                f"quarter {q} holds month "
                + ", ".join(str(m) for m in sorted(months) if quarter_of_month(m) == q)
                for q in quarters
            )
            collector.add(
                "QP030",
                (
                    "Months in this submission span more than one calendar "
                    f"quarter: {grouped}. A quarterly report covers the three "
                    "months of a single quarter, so split these rows into one "
                    "file per quarter and submit them separately."
                ),
            )
    years = seen["years"]
    if len(years) > 1:
        collector.add(
            "QP031",
            (
                "Rows in this submission carry more than one reporting year "
                f"({', '.join(sorted(years))}). A report covers one quarter of "
                "one year, so split these rows by year and submit each "
                "reporting period separately."
            ),
        )


def _column_dependent_rule_ids(specs: Sequence[RuleSpec]) -> list[str]:
    return [spec.id for spec in specs if spec.implemented and spec.id not in _HEADER_INDEPENDENT]


def _next_row(rows: Iterator[list[str]]) -> list[str] | None:
    try:
        return next(rows)
    except StopIteration:
        return None
    except csv.Error as exc:
        raise _CsvParseFailure(str(exc)) from exc


def _scan_rows(
    collector: _Collector,
    profile: Profile,
    rows: Iterator[list[str]],
    header_ok: bool,
) -> int:
    """Walk the data rows. Returns the number of non-blank data rows seen."""
    expected_width = len(profile.header)
    seen: dict[str, set[str]] = {"months": set(), "years": set()}
    data_rows = 0
    offset = 1

    while True:
        row = _next_row(rows)
        if row is None:
            break
        offset += 1
        if not any(cell.strip() for cell in row):
            collector.add(
                "QP004",
                (
                    "Row is blank. The instructions exclude blank rows from a "
                    "submission, so delete this row."
                ),
                row=offset,
            )
            continue
        data_rows += 1
        if not header_ok:
            continue
        if len(row) != expected_width:
            collector.add("QP003", _width_message(profile, row, expected_width), row=offset)
            continue
        _row_checks(collector, profile, row, offset, seen)

    if header_ok:
        _cross_row_checks(collector, seen)
    return data_rows


def _read_and_scan(
    report: Report,
    collector: _Collector,
    specs: Sequence[RuleSpec],
    profile: Profile,
    rows: Iterator[list[str]],
) -> Report:
    try:
        header = _next_row(rows)
    except _CsvParseFailure as failure:
        return _parse_failure(report, specs, profile, failure.detail, collector)

    if header is None:
        _blocked(
            collector,
            "The file could not be parsed as CSV.",
            "The submission could not be parsed, so this rule was never applied.",
        )
        return _finish(report, collector, 0)

    header_ok = _check_header(collector, profile, header)
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
    try:
        data_rows = _scan_rows(collector, profile, rows, header_ok)
    except _CsvParseFailure as failure:
        return _parse_failure(report, specs, profile, failure.detail, collector)

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
            (
                "The file contains a header but no data rows, so nothing was "
                "validated. A submission reports monthly data for the previous "
                "quarter, so add one row per reporting combination beneath the "
                "header before submitting."
            ),
        )

    return _finish(report, collector, data_rows)


def _width_message(profile: Profile, row: Sequence[str], expected_width: int) -> str:
    message = (
        f"Row has {len(row)} fields but the template defines {expected_width}. "
        f"Every row needs exactly {expected_width} comma-separated values, in "
        "the template's order."
    )
    if len(row) > expected_width:
        return message + (
            " A comma inside a value splits it into two fields unless the "
            'value is wrapped in double quotation marks, so "Smith, J" counts '
            "as one field and Smith, J counts as two."
        )
    missing = list(profile.header[len(row) :])
    if missing:
        message += " Counting from the left, the row stops before " + ", ".join(missing) + "."
    return message


def _blocked(collector: _Collector, detail: str, reason: str) -> None:
    collector.add("QP001", detail)
    collector.block_all_except(["QP001"], reason)


def _empty_detail(ingest: _Ingest) -> str:
    """Say which kind of nothing the file holds, since they are not the same."""
    if ingest.had_bom and not ingest.tail_nonempty:
        return (
            "The file holds nothing but a UTF-8 byte order mark , the "
            "bytes EF BB BF. There is no header row and no data."
        ).replace("  ", " ")
    if ingest.had_bom and not ingest.tail_has_nonspace:
        return (
            "The file holds nothing but a UTF-8 byte order mark and "
            "whitespace, the bytes EF BB BF. There is no header row and no "
            "data."
        )
    if not ingest.size:
        return "The file is empty, with no bytes in it at all."
    return (
        f"The file holds {ingest.size} bytes of whitespace and nothing else. "
        "There is no header row and no data."
    )


def _validate_ingest(
    ingest: _Ingest,
    profile: Profile,
    input_name: str,
    reopen: Callable[[], io.BufferedIOBase],
) -> Report:
    """Drive the fail-closed decision tree from what one pass observed.

    The tree and its order are exactly the ones `validate_bytes` has always
    walked: the byte order mark before the decode question, the decode
    question before emptiness, line endings before truncation, and rows only
    once every earlier gate has opened. `reopen` supplies a fresh binary
    stream positioned at the start for the row-by-row pass, which streams so
    that memory does not grow with the filing.
    """
    specs = specs_for(profile)
    collector = _Collector(specs, profile)
    collector.register_unimplemented()

    report = Report(
        tool=TOOL_NAME,
        tool_version=__version__,
        profile_id=profile.id,
        profile_title=profile.title,
        input_name=input_name,
        input_sha256=ingest.sha256,
    )

    collector.mark_evaluated("QP001")
    # Before the decode, not after it. A byte order mark is a fact about the
    # file, and it is still a fact when the file turns out not to be UTF-8.
    _bom_advisory(collector, ingest.had_bom)

    if ingest.decode_detail is not None:
        _blocked(
            collector,
            (
                f"The file is not valid UTF-8 text: {ingest.decode_detail}. This tool "
                "reads UTF-8, so it could not open the file and validated "
                "nothing in it. Re-save the file as UTF-8 and run it again."
            ),
            "The submission could not be read, so this rule was never applied.",
        )
        return _finish(report, collector, 0)

    if not ingest.has_content:
        _blocked(
            collector,
            f"{_empty_detail(ingest)} Nothing in it could be validated.",
            "The submission could not be read, so this rule was never applied.",
        )
        return _finish(report, collector, 0)

    _line_ending_advisory(collector, ingest.crlf, ingest.lf, ingest.cr)

    if ingest.truncated_quote:
        _blocked(
            collector,
            (
                "The file ends in the middle of a quoted value: a double "
                "quotation mark opens a field that is never closed before the "
                "end of the file. That means the file was cut off, most often "
                "by an interrupted export or a partial copy. Every value after "
                "the opening quotation mark is unreliable, so no other rule "
                "was applied. Re-export the file and check that it ends with a "
                "complete final row."
            ),
            "The submission was cut off mid-value, so this rule was never applied.",
        )
        return _finish(report, collector, 0)

    binary = reopen()
    try:
        # typeshed narrows the buffer more tightly than either BufferedReader
        # or BytesIO can be expressed through one callable's return type.
        text_stream = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")  # type: ignore[type-var]
        rows = iter(csv.reader(text_stream))
        return _read_and_scan(report, collector, specs, profile, rows)
    finally:
        binary.close()


def validate_bytes(data: bytes, profile: Profile, input_name: str) -> Report:
    """Validate one submission held in memory.

    This and `validate_path` are two entrances to one implementation. The
    bytes here already sit in memory by the caller's choice, so nothing is
    saved by pretending otherwise; the pass still runs through the same
    bounded scanner so both entrances observe identical behaviour.
    """
    ingest = _scan_stream(io.BytesIO(data))
    return _validate_ingest(
        ingest,
        profile,
        input_name,
        lambda: io.BytesIO(data),
    )


def validate_path(path: str, profile: Profile) -> Report:
    """Validate a submission on disk.

    Two passes, each bounded: this one collects the file-level facts without
    retaining content, and the second hands rows to the checker as they are
    read. Peak memory grows with the longest row, not with the size of the
    filing.
    """
    with open(path, "rb") as handle:
        ingest = _scan_stream(handle)

    def reopen() -> io.BufferedIOBase:
        return open(path, "rb")

    return _validate_ingest(ingest, profile, os.path.basename(path), reopen)


def _parse_failure(
    report: Report,
    specs: Sequence[RuleSpec],
    profile: Profile,
    detail: str,
    abandoned: _Collector,
) -> Report:
    """Throw away every finding gathered before the reader gave up.

    A file that stops parsing part way through has not been checked, not even
    the part that parsed, because the reader cannot know what the rest of it
    would have said. Reporting the findings from the readable prefix alongside
    a parse error would invite reading the prefix as validated. It was not.

    What does survive is what was observed about the file rather than about
    its contents. A byte order mark on the front, and line endings that do not
    agree with each other, are true of the bytes whether or not the CSV reader
    reached the end of them, and are worth knowing precisely because one of
    them may be why it did not. Throwing those away with the findings was
    discarding an observation the reader had already made and could still
    stand behind. See ADR 0006.
    """
    fresh = _Collector(specs, profile)
    fresh.register_unimplemented()
    fresh.mark_evaluated("QP001")
    _blocked(
        fresh,
        (
            f"The file could not be parsed as CSV: {detail}. No rule was "
            "applied to any part of it, including the rows before the point "
            "where parsing stopped. Any advisory below describes the file "
            "itself and still stands."
        ),
        "The submission could not be parsed, so this rule was never applied.",
    )
    fresh.readvise(abandoned.file_observations())
    return _finish(report, fresh, 0)


def _finish(report: Report, collector: _Collector, rows_read: int) -> Report:
    report.findings = collector.findings
    report.rules_evaluated = collector.evaluated
    report.rules_not_evaluated = collector.not_evaluated
    report.advisories = collector.advisories
    report.rows_read = rows_read
    _refuse_contradictions(report, collector.registered)
    return report


def _refuse_contradictions(report: Report, registered: frozenset[str]) -> None:
    """Hold the report to what `model.Report` says a report is.

    Three ways a report can contradict itself, all of them resolved in the
    reader's favour and therefore all of them worse than a crash:

    1. It cites a rule in a finding that it does not list as evaluated,
       claiming a check it also admits it did not run.
    2. It lists the same rule as evaluated and as not evaluated, saying both
       at once about one check.
    3. It applies a rule to this profile and then mentions it in neither list,
       so the rule leaves no trace in the output and a reader cannot tell it
       was meant to run at all.

    `model.Report` states the second and third as one invariant: every rule
    applicable to a profile ends up in exactly one of `rules_evaluated` or
    `rules_not_evaluated`. Every gating path in this module satisfies it by
    construction today, through two independent lines in `_Collector`. Either
    of those can be removed without any input behaving differently, which is
    the reason the invariant is asserted here rather than left to them.
    """
    evaluated = set(report.rules_evaluated)
    not_evaluated = {item.rule_id for item in report.rules_not_evaluated}

    orphaned = sorted({f.rule_id for f in report.checked_findings() if f.rule_id not in evaluated})
    if orphaned:
        raise ValueError(
            f"report cites {', '.join(orphaned)} in its findings but does not list "
            "the rule as evaluated, so the report contradicts itself"
        )

    both = sorted(evaluated & not_evaluated)
    if both:
        raise ValueError(
            f"report lists {', '.join(both)} as evaluated and as not evaluated. A "
            "rule is one or the other, and a reader given both learns nothing "
            "about whether the check ran"
        )

    unaccounted = sorted(registered - evaluated - not_evaluated)
    if unaccounted:
        raise ValueError(
            f"report applies {', '.join(unaccounted)} to this profile but lists the "
            "rule as neither evaluated nor unevaluated, so the report is silent "
            "about a check the reader has no way to ask after"
        )
