"""Reading a filing's header row, and matching it to a published template.

This is the mechanism the command line has always used, lifted out of
`cli.py` so that the published Python API in `api.py` can reach the same
code rather than a second copy of it. The command line keeps its own refusal
wording, which names the path the user typed; what moved here is the part
that must not diverge: how many bytes get read, how they are decoded, and
what counts as a match.

Two properties are load-bearing and are the reason this is not simply
`open(path).readline()`.

**Only the first record is read, and only it is decoded.** Opening a text
handle looks like it reads the header and does not: `TextIOWrapper` decodes a
whole read-ahead block to satisfy one `next()`, so an invalid byte thousands
of bytes past the header was raised while reading the header, and reported as
a fact about the first row. The same defect a little further into the file
detected fine and got a report naming the offending byte. Which of the two a
filing received depended only on where its bad byte fell relative to an 8 KB
window that nothing documents.

**Detection never guesses.** A header matches a published template exactly,
transcribed typos included, because those are the rows the portal expects.
Zero matches and several matches are both refusals. Validating a filing
against the wrong form would produce findings about columns that mean
something else, which is worse than producing none.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence

from .profiles import PROFILES, Profile, detect_profiles

QUOTE = 0x22
COMMA = 0x2C
LINE_BREAKS = (0x0D, 0x0A)

# How much of the file to take at a time while looking for the end of the
# header. Large enough that a published header arrives in the first read, small
# enough that it is not a meaningful amount of memory.
HEADER_CHUNK_BYTES = 1 << 16

# How many near misses a refusal lists. A refusal that printed all five
# profiles would be telling the caller the registry rather than telling them
# which form their file nearly is.
_NEAR_MISS_LIMIT = 3


class ProfileDetectionError(Exception):
    """Detection declined to say which published form a filing is.

    Carries the machine-readable reason alongside the sentence, so a caller
    can branch on `reason` without parsing prose:

    * `unreadable` - the first record is not UTF-8 CSV.
    * `empty` - the file has no rows at all.
    * `no_match` - the header matches no published template byte for byte.
    * `ambiguous` - the header matches more than one.

    `near_misses` holds profile identifiers ranked by how many published
    column names the header shares with them, best first. It is advice for a
    person, never a fallback: nothing in this module ever validates against a
    near miss, because a header that is close to a template is exactly the
    case where the wrong columns carry plausible values.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        matches: Sequence[str] = (),
        near_misses: Sequence[str] = (),
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.matches = tuple(matches)
        self.near_misses = tuple(near_misses)


class HeaderScan:
    """Walks raw bytes looking for the end of the first CSV record.

    Only three bytes decide where a record ends: the quotation mark, which
    opens and closes a field a line break may sit inside, and the two line
    break characters themselves. All three are ASCII, and no ASCII byte ever
    appears inside a multi-byte UTF-8 sequence, so this can run on undecoded
    bytes without ever matching part of a character. That is the point: the
    bytes past the header must not be decoded at all.
    """

    __slots__ = ("_at_field_start", "_in_quotes", "_position")

    def __init__(self) -> None:
        self._at_field_start = True
        self._in_quotes = False
        self._position = 0

    def end_within(self, buffer: bytes | bytearray) -> int | None:
        """The index of the line break that ends the first record, if it is here.

        Resumable: the position and the quote state carry across calls, so the
        caller can keep handing over a longer buffer as it reads.
        """
        while self._position < len(buffer):
            byte = buffer[self._position]
            if self._in_quotes:
                if byte != QUOTE:
                    self._position += 1
                elif self._position + 1 >= len(buffer):
                    return None  # a doubled quote and a closing one look alike here
                elif buffer[self._position + 1] == QUOTE:
                    self._position += 2
                else:
                    self._in_quotes = False
                    self._at_field_start = False
                    self._position += 1
                continue
            if byte in LINE_BREAKS:
                return self._position
            self._in_quotes = self._at_field_start and byte == QUOTE
            self._at_field_start = byte == COMMA
            self._position += 1
        return None


def read_header_bytes(path: str) -> bytes:
    """The bytes of the file's first CSV record, and not one byte more.

    A file with no line break at all is one long record, so it is read whole,
    which is the same shape of cost the validation run already accepts: peak
    memory grows with the longest row, not with the size of the filing.
    """
    scan = HeaderScan()
    buffer = bytearray()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(HEADER_CHUNK_BYTES)
            if not block:
                return bytes(buffer)
            buffer.extend(block)
            end = scan.end_within(buffer)
            if end is not None:
                return bytes(buffer[:end])


def header_bytes_of(data: bytes) -> bytes:
    """The first CSV record of a filing already held in memory.

    The same scan `read_header_bytes` runs against a file, so a caller who
    validates bytes and a caller who validates a path detect identically.
    """
    end = HeaderScan().end_within(data)
    return data if end is None else bytes(data[:end])


def header_row(header_bytes: bytes) -> list[str]:
    """The header as fields, or a refusal saying why it could not be read.

    A byte order mark is stripped for the comparison and is still reported by
    the validation run as `ADV-BOM`. Detection does not get to silence an
    advisory by consuming the bytes that raise it.
    """
    try:
        row = next(csv.reader([header_bytes.decode("utf-8-sig")]), None)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ProfileDetectionError(
            "the first row could not be read as UTF-8 CSV",
            reason="unreadable",
        ) from exc
    if not row:
        raise ProfileDetectionError("the file has no rows", reason="empty")
    return row


def near_misses(header: Sequence[str]) -> tuple[str, ...]:
    """Profile identifiers ranked by how much of their header this row shares.

    Ranked on the set of column names rather than on position, because the
    two failures a filer actually makes are a reordered header and a header
    with one column added or dropped, and both keep most of the names. A
    profile sharing nothing is left out rather than listed last: naming it
    would imply it was under consideration.
    """
    row = set(header)
    scored = []
    for profile in PROFILES.values():
        published = set(profile.header)
        shared = len(row & published)
        if shared:
            scored.append((-shared, profile.id))
    scored.sort()
    return tuple(profile_id for _, profile_id in scored[:_NEAR_MISS_LIMIT])


def detect_profile(header_bytes: bytes) -> Profile:
    """The one published profile this header matches, or a refusal.

    `header_bytes` is the first CSV record and nothing after it; pass
    `read_header_bytes(path)` or `header_bytes_of(data)` rather than a whole
    filing, so that a bad byte in row nine thousand cannot be reported as a
    fact about the header.
    """
    header = header_row(header_bytes)
    matches = detect_profiles(header)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        close = near_misses(header)
        detail = f"; closest published templates: {', '.join(close)}" if close else ""
        raise ProfileDetectionError(
            f"the header does not match any published template byte for byte{detail}",
            reason="no_match",
            near_misses=close,
        )
    ids = sorted(profile.id for profile in matches)
    raise ProfileDetectionError(
        f"the header matches several published templates ({', '.join(ids)})",
        reason="ambiguous",
        matches=ids,
    )
