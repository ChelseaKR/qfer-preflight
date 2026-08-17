"""Turning values and header rows into something a filer can act on.

Nothing in this module decides whether anything is wrong. It renders what is
actually in the file, in words, so a finding can name the difference between
what the file holds and what the published template asks for.

The reason it exists: a cell holding a space and a cell holding a non-breaking
space look identical in a spreadsheet, and identical in a naive error message
that prints the value back. They are not identical to a validator. A filer who
is told only that "CustomerType value 'B ' is not a published value" has been
told their correct-looking value is wrong and given no way to see why. Naming
the character is the difference between a report that closes the loop and one
that starts an email thread.
"""

from __future__ import annotations

from collections.abc import Sequence

# Characters that are invisible, or near enough, in a spreadsheet cell. The
# names are plain English on purpose: the audience is a compliance officer
# looking at Excel, not a developer looking at a hex dump.
_CHARACTER_NAMES: dict[str, str] = {
    "\t": "a tab",
    "\n": "a line feed",
    "\r": "a carriage return",
    "\x00": "a NUL byte",
    "\x0b": "a vertical tab",
    "\x0c": "a form feed",
    "\x1c": "a file separator character",
    "\x1d": "a group separator character",
    "\x1e": "a record separator character",
    "\x1f": "a unit separator character",
    "\x7f": "a delete character",
    "\xa0": "a non-breaking space",
    "\xad": "a soft hyphen",
    "\u180e": "a Mongolian vowel separator",
    "\u2007": "a figure space",
    "\u200b": "a zero-width space",
    "\u200c": "a zero-width non-joiner",
    "\u200d": "a zero-width joiner",
    "\u202f": "a narrow no-break space",
    "\u2060": "a word joiner",
    "\u3000": "an ideographic space",
    "\ufeff": "a byte order mark",
}

# The characters a spreadsheet may read as the start of a formula rather than
# as text. This is not a CEC rule and is never reported as one. See ADR 0004.
FORMULA_LEAD_CHARACTERS = ("=", "@", "+", "-", "\t", "\r")

_ASCII_DIGITS = frozenset("0123456789")


def character_name(char: str) -> str:
    """A readable name for one character.

    The code point is included whenever the character is invisible or is not
    plain ASCII, because those are the ones a filer cannot identify by looking.
    An ordinary comma or dollar sign is named without one; "contains ','" is
    clearer than "contains ',' (U+002C)".
    """
    named = _CHARACTER_NAMES.get(char)
    point = f"U+{ord(char):04X}"
    if named:
        return f"{named} ({point})"
    if char == " ":
        return f"a space ({point})"
    if not char.isprintable():
        return f"an unprintable character ({point})"
    if char.isascii():
        return repr(char)
    return f"{char!r} ({point})"


def _is_hidden(char: str) -> bool:
    """True when a spreadsheet would show nothing, or nothing distinctive."""
    if char in _CHARACTER_NAMES:
        return True
    return not char.isprintable()


def visible(value: str) -> str:
    """The value with every invisible character replaced by its code point."""
    return "".join(f"<U+{ord(ch):04X}>" if _is_hidden(ch) else ch for ch in value)


def show(value: str) -> str:
    """How a cell value should appear inside a finding message."""
    if not value:
        return "an empty cell"
    if not value.strip():
        return f'"{visible(value)}" (whitespace only)'
    return f'"{visible(value)}"'


def _edge_whitespace_note(value: str) -> str | None:
    leading = value[: len(value) - len(value.lstrip())]
    trailing = value[len(value.rstrip()) :]
    if not leading and not trailing:
        return None
    edges = []
    if leading:
        edges.append(f"begins with {character_name(leading[0])}")
    if trailing:
        edges.append(f"ends with {character_name(trailing[-1])}")
    return f"The cell {' and '.join(edges)}. Delete the surrounding whitespace."


def _interior_note(value: str) -> str | None:
    interior = sorted({ch for ch in value.strip() if _is_hidden(ch)})
    if not interior:
        return None
    names = ", ".join(character_name(ch) for ch in interior)
    plural = "characters that are" if len(interior) > 1 else "a character that is"
    return (
        f"The cell contains {plural} invisible in a spreadsheet: {names}. "
        "Retype the value rather than editing around it."
    )


def _digit_note(value: str) -> str | None:
    foreign = sorted({ch for ch in value if ch.isdigit() and ch not in _ASCII_DIGITS})
    if not foreign:
        return None
    names = ", ".join(character_name(ch) for ch in foreign)
    return (
        f"The cell holds a digit that is not a plain 0 to 9 digit: {names}. "
        "It reads as a number but is not one. Retype it using ordinary digits."
    )


def cell_note(value: str) -> str:
    """A sentence explaining anything about the cell the eye cannot catch.

    Returns the empty string when the value holds no surprises, so a caller can
    append it unconditionally.
    """
    notes = [
        note
        for note in (_edge_whitespace_note(value), _interior_note(value), _digit_note(value))
        if note
    ]
    return (" " + " ".join(notes)) if notes else ""


def column_letter(index: int) -> str:
    """The spreadsheet column letter for a zero-based column index."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def formula_lead(value: str) -> str | None:
    """The leading character a spreadsheet may treat as the start of a formula.

    A leading plus or minus is ordinary in a reported amount, so it only counts
    when the rest of the cell is not a plain number.
    """
    if not value:
        return None
    lead = value[0]
    if lead not in FORMULA_LEAD_CHARACTERS:
        return None
    if lead in "+-" and _is_plain_number(value):
        return None
    return lead


def _is_plain_number(value: str) -> bool:
    body = value[1:] if value[:1] in "+-" else value
    if not body:
        return False
    whole, dot, fraction = body.partition(".")
    if dot and not fraction:
        return False
    digits = whole + fraction
    return bool(digits) and all(ch in _ASCII_DIGITS for ch in digits)


def hidden_characters(value: str) -> list[str]:
    """Every invisible character in the value, deduplicated and sorted."""
    return sorted({ch for ch in value if _is_hidden(ch)})


# ---------------------------------------------------------------------------
# Header comparison
# ---------------------------------------------------------------------------

_DELIMITER_NAMES = {
    "\t": "tabs",
    ";": "semicolons",
    "|": "pipes",
    ":": "colons",
}

_MAX_DETAIL_LINES = 8


def _delimiter_guess(actual: Sequence[str]) -> str | None:
    """Name the separator a single-column header row appears to really use."""
    if len(actual) != 1:
        return None
    only = actual[0]
    for char, name in _DELIMITER_NAMES.items():
        if only.count(char) >= 2:
            return name
    return None


_WHITESPACE = "whitespace"
_CASE = "case"
_ORDER = "order"
_OTHER = "other"


def _kind(expected: str, found: str, expected_all: Sequence[str]) -> str:
    if found.strip() == expected.strip():
        return _WHITESPACE
    if found.strip().casefold() == expected.strip().casefold():
        return _CASE
    if found in expected_all:
        return _ORDER
    return _OTHER


_KIND_PHRASES = {
    _WHITESPACE: ", which is the right name with whitespace around it",
    _CASE: ", which differs only in capitalisation",
    _ORDER: ", which the template puts in a different position",
    _OTHER: "",
}


def _position_differences(expected: Sequence[str], actual: Sequence[str]) -> list[tuple[str, str]]:
    """Every position where the two headers differ, paired with its kind."""
    out = []
    for index in range(min(len(expected), len(actual))):
        want, got = expected[index], actual[index]
        if want == got:
            continue
        kind = _kind(want, got, expected)
        out.append(
            (
                kind,
                f'column {column_letter(index)}: the template has "{want}" but '
                f'found "{visible(got)}"{_KIND_PHRASES[kind]}',
            )
        )
    return out


def _membership_lines(expected: Sequence[str], actual: Sequence[str]) -> list[str]:
    lines = []
    missing = [name for name in expected if name not in actual]
    unexpected = [name for name in actual if name not in expected]
    if missing:
        lines.append("missing column names: " + ", ".join(f'"{n}"' for n in missing))
    if unexpected:
        lines.append(
            "column names the template does not have: "
            + ", ".join(f'"{visible(n)}"' for n in unexpected[:_MAX_DETAIL_LINES])
        )
    return lines


def _uniform_summary(differences: list[tuple[str, str]], expected: Sequence[str]) -> str | None:
    """One sentence for the case where every column has the same small defect."""
    kinds = {kind for kind, _ in differences}
    if len(differences) < 2 or len(kinds) != 1:
        return None
    only = kinds.pop()
    if only == _WHITESPACE:
        return (
            f"All {len(differences)} mismatched column names are correct apart "
            "from whitespace around them. Delete the spaces between the commas "
            "and the names."
        )
    if only == _CASE:
        return (
            f"All {len(differences)} mismatched column names are correct apart "
            "from capitalisation. The template's spelling is authoritative, "
            "including its lower case letters."
        )
    if only == _ORDER and len(differences) == len(expected):
        return (
            "The column names are all present but in a different order. The "
            "template's order is what the portal reads, so reorder the columns "
            "to match it."
        )
    return None


def _detail_sentence(details: list[str]) -> str:
    shown = details[:_MAX_DETAIL_LINES]
    remainder = len(details) - len(shown)
    listed = "; ".join(shown)
    if remainder:
        listed += f"; and {remainder} further difference{'s' if remainder > 1 else ''}"
    return f"Differences: {listed}."


def header_report(expected: Sequence[str], actual: Sequence[str]) -> str:
    """Explain how a header row differs from the published template."""
    parts = ["Header row does not match the published template."]
    delimiter = _delimiter_guess(actual)

    if delimiter:
        # Everything past this point would just re-describe the one long cell.
        parts.append(
            "The whole line parsed as a single column name because it separates "
            f"names with {delimiter} rather than commas. Re-export the file as "
            "comma separated values."
        )
    else:
        parts.extend(_difference_parts(expected, actual))

    parts.append(
        "Replace the first line of the file with the template header, exactly "
        "as published and in this order: " + ",".join(expected)
    )
    return " ".join(parts)


def _difference_parts(expected: Sequence[str], actual: Sequence[str]) -> list[str]:
    parts = []
    if len(actual) != len(expected):
        names = "column name" if len(actual) == 1 else "column names"
        parts.append(f"The header row has {len(actual)} {names}; the template has {len(expected)}.")

    differences = _position_differences(expected, actual)
    summary = _uniform_summary(differences, expected)
    if summary:
        return [*parts, summary]

    details = [text for _, text in differences]
    if len(actual) != 1:
        details += _membership_lines(expected, actual)
    if details:
        parts.append(_detail_sentence(details))
    return parts
