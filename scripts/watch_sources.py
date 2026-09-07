#!/usr/bin/env python3
"""Re-fetch every document in `docs/source-manifest.md` and report digest drift.

The README says, in terms, that "published documents change, and when they do this tool
is wrong until it is updated". `docs/source-manifest.md` turns that into a procedure a
person follows before each filing deadline. A promise kept by hand before a deadline is a
promise that lapses quietly, so this script is the same procedure on a schedule.

## Three outcomes, and the middle one is the whole point

`UNCHANGED`  the document re-hashes to the recorded digest.
`DRIFTED`    it re-hashes to something else. The published text moved, and every rule
             quoting it may now be quoting a superseded revision.
`ERROR`      **we could not look.** A 404, a timeout, a refused connection, a 500.

`ERROR` is not `UNCHANGED`, and collapsing the two is the specific failure this script
exists to avoid. A watcher that reported "no drift" because the Commission's web server
was down would be worse than no watcher: it would be a green light nobody had earned.
The exit code says so -- 0 only when every document was actually fetched and every digest
matched -- and the JSON summary carries the three counts separately so nothing downstream
has to infer it.

## What this script does NOT do

It does not re-transcribe a quote, move a severity, or update a digest. `source-manifest.md`
says why: a changed hash means a rule may be quoting superseded text, and deciding what
that means is a person's ADR. This opens a review request and stops.

It is also not part of the validator. Nothing here is imported by `qfer_preflight`, and
the runtime remains offline: this reads the manifest and the rule registry, and it is run
by a workflow and by hand, never by `check`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "source-manifest.md"

#: A `### heading` starts an entry. Sections are split on this rather than matched as
#: one big pattern, because the fields sit in a bulleted list with blank lines around it
#: and a single regex spanning them is brittle in exactly the way that reads as "no
#: entries found" rather than as an error.
_HEADING = re.compile(r"^### (.+?)$", re.MULTILINE)
_URL = re.compile(r"^- url: (\S+)$", re.MULTILINE)
_SHA256 = re.compile(r"^- sha256: ([0-9a-f]{64})$", re.MULTILINE)
_RETRIEVED = re.compile(r"^- retrieved: ([0-9]{4}-[0-9]{2}-[0-9]{2})$", re.MULTILINE)

#: Long enough that a slow Commission PDF is not called an outage, short enough that a
#: hung connection does not hold a scheduled job open.
_TIMEOUT_SECONDS = 60

_USER_AGENT = "qfer-preflight source watch (https://github.com/ChelseaKR/qfer-preflight)"


class Outcome(StrEnum):
    """What re-fetching one manifest entry established."""

    UNCHANGED = "unchanged"
    DRIFTED = "drifted"
    #: Could not fetch. NOT unchanged. See the module docstring.
    ERROR = "error"
    #: `--dry-run`: we did not even try. Emphatically not unchanged. Without this the
    #: dry run reported "13 unchanged" and printed "Every cited document re-hashes as
    #: recorded" while making no network call at all, which is the defect this script
    #: was written to prevent, committed by the script itself.
    NOT_CHECKED = "not-checked"


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    title: str
    url: str
    sha256: str
    retrieved: str


@dataclass(frozen=True, slots=True)
class Result:
    entry: ManifestEntry
    outcome: Outcome
    #: The digest we got. `None` when we never got bytes at all, which is exactly the
    #: state that must not be rendered as a digest that happened to match.
    observed_sha256: str | None = None
    detail: str = ""
    #: Rule identifiers whose citation points at this URL, so triage starts from the
    #: registry rather than from a full-text diff.
    rules: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.entry.title,
            "url": self.entry.url,
            "recorded_sha256": self.entry.sha256,
            "observed_sha256": self.observed_sha256,
            "retrieved": self.entry.retrieved,
            "outcome": str(self.outcome),
            "detail": self.detail,
            "rules": list(self.rules),
        }


def parse_manifest(text: str) -> list[ManifestEntry]:
    """Every `### ` section carrying a url, a digest and a retrieval date.

    A section missing any of the three is skipped rather than half-parsed: an entry
    with no digest is not an entry that matches, and inventing a field to make the
    parse succeed is how a watcher starts reporting on documents it is not watching.
    `tests/test_source_manifest.py` is what keeps the manifest complete; this only
    reads what is there.
    """
    entries: list[ManifestEntry] = []
    headings = list(_HEADING.finditer(text))
    for index, heading in enumerate(headings):
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[start:end]
        url = _URL.search(section)
        sha256 = _SHA256.search(section)
        retrieved = _RETRIEVED.search(section)
        if url is None or sha256 is None or retrieved is None:
            continue
        entries.append(
            ManifestEntry(
                title=heading.group(1).strip(),
                url=url.group(1),
                sha256=sha256.group(1),
                retrieved=retrieved.group(1),
            )
        )
    return entries


def rules_citing(url: str) -> tuple[str, ...]:
    """Rule identifiers whose citation names `url`.

    Imported lazily so that `--help` and a manifest parse do not need the package, and
    so that a failure to import the registry cannot be mistaken for "no rules cite this".
    """
    from qfer_preflight.rules import all_rules

    return tuple(
        sorted(rule.id for rule in all_rules() if rule.citation and rule.citation.url == url)
    )


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        return bytes(response.read())


def check_entry(entry: ManifestEntry, *, dry_run: bool) -> Result:
    """One entry. A failed fetch is an ERROR outcome and never an UNCHANGED one."""
    rules = rules_citing(entry.url)
    if dry_run:
        return Result(
            entry=entry,
            outcome=Outcome.NOT_CHECKED,
            observed_sha256=None,
            detail="dry run: no request was made, so this document was not checked",
            rules=rules,
        )
    try:
        body = fetch(entry.url)
    except urllib.error.HTTPError as exc:
        return Result(
            entry=entry,
            outcome=Outcome.ERROR,
            detail=f"HTTP {exc.code} fetching {entry.url}: could not check, NOT unchanged",
            rules=rules,
        )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return Result(
            entry=entry,
            outcome=Outcome.ERROR,
            detail=f"could not fetch {entry.url}: {exc}: could not check, NOT unchanged",
            rules=rules,
        )

    observed = hashlib.sha256(body).hexdigest()
    if observed == entry.sha256:
        return Result(entry=entry, outcome=Outcome.UNCHANGED, observed_sha256=observed, rules=rules)
    return Result(
        entry=entry,
        outcome=Outcome.DRIFTED,
        observed_sha256=observed,
        detail=(
            f"recorded {entry.sha256}, re-fetched {observed}. The published text moved; "
            "any rule quoting it may be quoting a superseded revision."
        ),
        rules=rules,
    )


def summarise(results: Sequence[Result]) -> dict[str, object]:
    counts = {outcome.value: 0 for outcome in Outcome}
    for result in results:
        counts[result.outcome.value] += 1
    return {
        "documents": len(results),
        "counts": counts,
        # Stated rather than left to be inferred from the counts, because "no drift" and
        # "no drift that we were able to look for" are different sentences.
        "every_document_was_fetched": (
            counts[Outcome.ERROR.value] == 0 and counts[Outcome.NOT_CHECKED.value] == 0
        ),
        "results": [result.to_dict() for result in results],
    }


def render(summary: dict[str, object]) -> str:
    counts = summary["counts"]
    assert isinstance(counts, dict)
    lines = [
        f"{summary['documents']} document(s): "
        f"{counts['unchanged']} unchanged, {counts['drifted']} drifted, "
        f"{counts['error']} could not be checked, "
        f"{counts['not-checked']} not checked"
    ]
    results = summary["results"]
    assert isinstance(results, list)
    for row in results:
        assert isinstance(row, dict)
        if row["outcome"] in {Outcome.UNCHANGED.value, Outcome.NOT_CHECKED.value}:
            continue
        lines.append(f"  {str(row['outcome']).upper():9s} {row['title']}")
        lines.append(f"      {row['url']}")
        lines.append(f"      {row['detail']}")
        if row["rules"]:
            rules = row["rules"]
            assert isinstance(rules, list)
            lines.append(f"      rules citing this document: {', '.join(rules)}")
    if counts["not-checked"]:
        lines.append(
            f"DRY RUN: {counts['not-checked']} document(s) were not fetched and not "
            "checked. This says the manifest parses and the rule lookup resolves. It "
            "says NOTHING about whether the published documents have changed."
        )
    elif not counts["drifted"] and not counts["error"]:
        lines.append("Every cited document re-hashes as recorded.")
    if counts["error"]:
        lines.append(
            "A document that could not be fetched is NOT a document that has not "
            "changed. This run did not establish that the sources are current."
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-fetch every document in the source manifest and report digest drift. "
            "Opens no pull request and changes no file."
        )
    )
    parser.add_argument(
        "--manifest", default=str(DEFAULT_MANIFEST), help="path to source-manifest.md"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "parse the manifest and resolve citing rules, but make NO network call. "
            "Reports every entry as unchanged and says so in the detail, so a dry run "
            "is never mistaken for a real result"
        ),
    )
    parser.add_argument("--json", action="store_true", help="write the summary as JSON")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"could not read {manifest_path}: {exc}", file=sys.stderr)
        return 2

    entries = parse_manifest(text)
    if not entries:
        # An empty parse would otherwise report "0 documents, 0 drifted" and exit 0,
        # which is a green run over nothing at all.
        print(
            f"no manifest entries parsed from {manifest_path}. A manifest that reads as "
            "empty is a broken watcher, not a clean one.",
            file=sys.stderr,
        )
        return 2

    results = [check_entry(entry, dry_run=args.dry_run) for entry in entries]
    summary = summarise(results)
    print(json.dumps(summary, indent=2, sort_keys=True) if args.json else render(summary), end="")

    counts = summary["counts"]
    assert isinstance(counts, dict)
    if counts[Outcome.ERROR.value]:
        return 2
    if counts[Outcome.DRIFTED.value]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
