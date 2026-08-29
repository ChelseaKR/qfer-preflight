"""The source manifest covers every document the code cites.

`docs/source-manifest.md` records a retrieval date and a SHA-256 for each
published document the tool cites. Its value depends on staying complete: a
cited document missing from the manifest is one whose revision would go
unnoticed. These assertions keep it complete.

The manifest is a dev-time snapshot record. Nothing at runtime reads it, and
no test here fetches anything; they only read the file and compare it with the
URLs already in `profiles.py`.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from qfer_preflight.profiles import PROFILES, WORKSHOP_DECK_URL

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DOC = ROOT / "docs" / "source-manifest.md"

_SHA256_LINE = re.compile(r"^- sha256: ([0-9a-f]{64})$", re.MULTILINE)
_URL_LINE = re.compile(r"^- url: (\S+)$", re.MULTILINE)
_DATE_LINE = re.compile(r"^- retrieved: ([0-9]{4}-[0-9]{2}-[0-9]{2})$", re.MULTILINE)


def _doc_text() -> str:
    assert MANIFEST_DOC.exists(), f"{MANIFEST_DOC} is missing"
    return MANIFEST_DOC.read_text(encoding="utf-8")


def _cited_document_urls() -> set[str]:
    """Every URL of a citable document named by the profiles.

    The program page is deliberately excluded: it is an HTML landing page that
    grounds no rule, and the manifest records why it carries no hash.
    """
    urls: set[str] = {WORKSHOP_DECK_URL}
    for profile in PROFILES.values():
        urls.add(profile.instructions_url)
        urls.add(profile.template_url)
    return urls


def _manifest_entries() -> list[tuple[str, str]]:
    """The `###` sections under `## Manifest`, as (heading, body) pairs.

    Only that part of the file records documents. `## Not a document` and
    `## Deliberately absent` describe things deliberately carrying no hash,
    and requiring a triple of them would be requiring the opposite of what
    they say.
    """
    text = _doc_text()
    start = text.index("\n## Manifest\n")
    body = text[start:]
    end = body.find("\n## ", 1)
    if end != -1:
        body = body[:end]
    entries: list[tuple[str, str]] = []
    for chunk in body.split("\n### ")[1:]:
        heading, _, rest = chunk.partition("\n")
        entries.append((heading.strip(), rest))
    return entries


def test_every_cited_document_appears_in_the_manifest() -> None:
    text = _doc_text()
    listed = set(_URL_LINE.findall(text))
    missing = sorted(_cited_document_urls() - listed)
    assert not missing, (
        f"documents cited by profiles but absent from {MANIFEST_DOC.name}: "
        f"{missing}. A cited document without a hash is one whose revision "
        "would go unnoticed"
    )


def test_manifest_entries_are_complete_triples() -> None:
    text = _doc_text()
    urls = _URL_LINE.findall(text)
    hashes = _SHA256_LINE.findall(text)
    dates = _DATE_LINE.findall(text)
    assert len(urls) == len(hashes) == len(dates), (
        f"{MANIFEST_DOC.name} has {len(urls)} urls, {len(hashes)} hashes and "
        f"{len(dates)} retrieval dates. Every entry needs all three"
    )
    assert len(urls) == len(set(urls)), f"{MANIFEST_DOC.name} lists a url twice"


def test_each_manifest_entry_carries_its_own_triple() -> None:
    """Per entry, not file-wide.

    The count above is a whole-file total, so an entry carrying two hashes
    beside a neighbour carrying none satisfies it. The manifest exists so that
    a silent revision announces itself, and it can only do that for a document
    whose own hash is recorded next to its own url.
    """
    sections = _manifest_entries()
    assert sections, "found no manifest entries, so this check would pass vacuously"

    for heading, body in sections:
        for label, pattern in (
            ("url", _URL_LINE),
            ("sha256", _SHA256_LINE),
            ("retrieved", _DATE_LINE),
        ):
            found = pattern.findall(body)
            assert len(found) == 1, (
                f"manifest entry {heading!r} carries {len(found)} {label} lines. "
                "Each entry needs exactly one, or the hash and the url it "
                "belongs to cannot be told apart"
            )


def test_retrieval_dates_are_real_calendar_dates() -> None:
    """A malformed date must fail this test, and fail it with an explanation.

    This used to read `assert date(year, month, day), "..."`. `datetime.date`
    defines no `__bool__`, so every date object is truthy and the assertion
    could never be False; its message was unreachable. What actually caught a
    bad date was the ValueError raised inside `date(...)`, which pytest reports
    as an error rather than a failure and with a stdlib message instead of the
    authored one. The construction is now the check, deliberately, and it says
    which line of the manifest is wrong.
    """
    dates = _DATE_LINE.findall(_doc_text())
    assert dates, f"{MANIFEST_DOC.name} records no retrieval dates at all"

    for raw in dates:
        year, month, day = (int(part) for part in raw.split("-"))
        try:
            date(year, month, day)
        except ValueError as exc:
            pytest.fail(f"{MANIFEST_DOC.name} records {raw!r}, which is not a real date: {exc}")


def test_the_date_check_rejects_a_date_that_does_not_exist() -> None:
    """The check above passes on today's manifest. This is why that means something."""
    with pytest.raises(ValueError):
        date(2026, 2, 30)
