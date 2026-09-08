"""Code sets the caller holds, which this project has never seen and does not vouch for.

This is deliberately not `codes.py`. That module opens by saying that every
table in it is transcribed from a primary source document published by the
Commission, and that nothing in it may be extended, guessed at, or inferred.
A list a filer hands in on the command line is none of those things: it is
whatever bytes were in the file, and this project cannot read the document it
came from, cannot check it against anything, and will never ship a copy of it.
Keeping the two in separate modules makes that difference structural rather
than a sentence somebody has to remember.

The whole reason this exists is QP018. The instructions require a NAICS Code to
"match the list of Valid NAICS codes" and the list is published nowhere; the
Commission has said it does not plan to publish it, because it carries custom
codes for particular utilities alongside CEC-defined internal ones (ADR 0009).
So the tool cannot check membership and says so on every run.

A filer with portal access can obtain the data dictionary that holds the list.
For that filer, and only while they are the one reading the report, the check is
a transcription job rather than a research one. `--naics-list` is that: the code
set comes from the person who holds it, the finding names the file's SHA-256 so
they can tell which list produced it, and the report says in words that it was
evaluated against a caller-supplied list rather than a published one.

ADR 0011 is the record of why that is not the thing ADR 0009 refused. In short:
ADR 0009 refused to ground a *finding* in private correspondence, because a
reader of the report cannot open the correspondence and so cannot tell a
grounded claim from an invented one. Here the ground is a file the reader
supplied, its digest is in the report, and the report never claims the list is
the Commission's.

Every refusal below is fail-closed and every one of them leaves QP018
unevaluated with the refusal named, rather than evaluating against a list that
is only partly what somebody meant. A code list read wrong is worse than no
code list: it produces confident errors against codes that are perfectly valid.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

# The published test for a NAICS Code's shape, which QP017 already enforces on
# every filing: "The code must be exactly 6 characters". A list holding
# anything else is not the list this rule needs, whatever it is.
NAICS_CODE_LENGTH = 6

_UTF8_BOM = b"\xef\xbb\xbf"


class CodeListRefused(Exception):
    """The supplied list is not one this tool will evaluate a rule against.

    Carries the sentence that goes into the report, so the reason a reader sees
    and the reason the caller sees on stderr are the same string rather than two
    renderings of one idea.
    """


@dataclass(frozen=True, slots=True)
class SuppliedNaicsList:
    """A caller's NAICS code list, and everything the report says about it.

    `path` is the path exactly as the caller wrote it, not a resolved absolute
    path. A report may be forwarded, and an absolute path discloses a directory
    layout that has nothing to do with the filing; the digest is what identifies
    the list, and it is the digest a filer compares when two reports disagree.
    """

    path: str
    sha256: str
    codes: frozenset[str]
    lines: int

    def provenance(self) -> dict[str, object]:
        """The report's record of this list. The codes themselves never appear.

        A report is a document a filer forwards. Reproducing a code set the
        Commission declined to publish, inside an artifact this tool writes,
        would be this project republishing somebody else's withheld material as
        a side effect of checking one column.
        """
        return {
            "rule": "QP018",
            "provenance": "caller_supplied",
            "path": self.path,
            "sha256": self.sha256,
            "codes": len(self.codes),
            "lines": self.lines,
            "note": (
                "This list was supplied on the command line. This tool publishes "
                "no NAICS code list, fetched nothing, and cannot check that this "
                "one is the Commission's. Every QP018 finding in this report is "
                "grounded in the file above and in nothing else."
            ),
        }


@dataclass(frozen=True, slots=True)
class NaicsListOffer:
    """What a caller offered, and what became of it. Three states, not two.

    "No list was supplied" and "a list was supplied and refused" are different
    facts about a run, and QP018 reports unevaluated in both. Collapsing them
    would leave a filer who mistyped a path reading the same report as one who
    never passed the flag, which is this project's own dominant defect: an
    absence rendered as the value it is not.

    `accepted` and `refusal` are exclusive and exactly one of them is set.
    """

    accepted: SuppliedNaicsList | None
    refusal: str | None

    def __post_init__(self) -> None:
        if (self.accepted is None) == (self.refusal is None):
            raise ValueError(
                "a NAICS list offer is either accepted or refused, never both and "
                "never neither; a run with no list supplied carries no offer at all"
            )


def offer_naics_list(path: str) -> NaicsListOffer:
    """Read a caller's list, returning the refusal rather than raising it.

    The refusal is a sentence the report carries, so it travels as a value. A
    caller who wants the exception can call :func:`load_naics_list` directly.
    """
    try:
        return NaicsListOffer(accepted=load_naics_list(path), refusal=None)
    except CodeListRefused as refused:
        return NaicsListOffer(accepted=None, refusal=str(refused))


def _refuse(path: str, detail: str) -> CodeListRefused:
    return CodeListRefused(
        f"A NAICS code list was supplied at {path} and refused: {detail} "
        "Membership of the Commission's list was therefore not checked, exactly "
        "as it is not checked when no list is supplied."
    )


def load_naics_list(path: str) -> SuppliedNaicsList:
    """Read a one-code-per-line NAICS list, or refuse and say why.

    The digest is taken over the file's bytes as read, before any decoding, so
    it identifies the file rather than this function's idea of it.

    Nothing here normalises. A line is stripped of its line ending and compared
    exactly, because a trailing space, a tab or a stray quotation mark in a code
    list is the sort of thing that silently turns a valid code into one that
    matches nothing -- and the resulting QP018 error would name a perfectly good
    filing as wrong. Refusing the list is the smaller mistake, and it is the one
    a person can fix.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise _refuse(path, f"it could not be read ({exc}).") from exc

    digest = hashlib.sha256(raw).hexdigest()

    if raw.startswith(_UTF8_BOM):
        raise _refuse(
            path,
            "it begins with a UTF-8 byte order mark, the bytes EF BB BF, which "
            "some editors add when saving. Those three bytes would join the "
            "first code and stop it matching anything, so re-save the file as "
            "UTF-8 without a byte order mark.",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _refuse(path, f"it is not valid UTF-8 text: {exc}.") from exc

    lines = text.splitlines()
    if not lines:
        raise _refuse(
            path,
            "it holds no lines at all. An empty list would refuse every code in "
            "the filing, which is a different claim from having no list.",
        )

    bad: list[str] = []
    codes: set[str] = set()
    for number, line in enumerate(lines, start=1):
        if len(line) != NAICS_CODE_LENGTH:
            bad.append(f"line {number} holds {line!r}, which is {len(line)} characters")
            if len(bad) == 5:
                break
            continue
        codes.add(line)

    if bad:
        listed = "; ".join(bad)
        raise _refuse(
            path,
            f"every line must be exactly {NAICS_CODE_LENGTH} characters and "
            f"{listed}. Line endings are stripped and nothing else is: a blank "
            "line, a comment, a header row or a trailing space all fail here, "
            "because none of them is a code and guessing which was meant is how "
            "a list quietly stops being the list somebody has.",
        )

    return SuppliedNaicsList(path=path, sha256=digest, codes=frozenset(codes), lines=len(lines))
