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
from pathlib import Path

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


def test_retrieval_dates_are_real_calendar_dates() -> None:
    from datetime import date

    for raw in _DATE_LINE.findall(_doc_text()):
        year, month, day = (int(part) for part in raw.split("-"))
        assert date(year, month, day), (
            f"{MANIFEST_DOC.name} records {raw}, which is not a real date"
        )
