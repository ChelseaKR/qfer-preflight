"""The column coverage map stays true to the registry and the profiles.

`docs/column-coverage.md` claims, for every column of every published
template, which rules touch it. Three things could silently break that claim:

  * a profile gains or reorders a column and the document drifts,
  * the document names a rule identifier the registry does not contain,
    which is how an invented check would enter through prose,
  * a rule is added to the registry and never mapped to any column.

Each has its own assertion here. Together they make the map load-bearing
rather than decorative: if this file passes, every cell of every header is
accounted for and every identifier in it is real.
"""

from __future__ import annotations

import re
from pathlib import Path

from qfer_preflight.model import ADVISORY_CODES
from qfer_preflight.profiles import PROFILES
from qfer_preflight.rules import RULE_SPECS_BY_ID

ROOT = Path(__file__).resolve().parents[1]
COVERAGE_DOC = ROOT / "docs" / "column-coverage.md"

_RULE_TOKEN = re.compile(r"\bQP[0-9]{3}\b")
_ADVISORY_TOKEN = re.compile(r"\bADV-[A-Z]+(?:-[A-Z]+)*\b")


def _doc_text() -> str:
    assert COVERAGE_DOC.exists(), f"{COVERAGE_DOC} is missing"
    return COVERAGE_DOC.read_text(encoding="utf-8")


def _columns_for_profile(text: str, profile_id: str) -> tuple[str, ...]:
    """Read the column table under the profile's heading, in order."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == f"## {profile_id}":
            start = i + 1
            break
    assert start is not None, f"no '## {profile_id}' section in {COVERAGE_DOC.name}"

    columns: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells[0] == "Column" or set(cells[0]) <= {"-", " ", ":"}:
            continue
        columns.append(cells[0])
    return tuple(columns)


def test_every_column_of_every_profile_is_mapped_in_order() -> None:
    text = _doc_text()
    for profile_id, profile in PROFILES.items():
        mapped = _columns_for_profile(text, profile_id)
        assert mapped == profile.header, (
            f"{COVERAGE_DOC.name} maps {profile_id} as {mapped}, but the "
            f"published template header is {profile.header}"
        )


def test_every_rule_identifier_named_in_the_doc_exists() -> None:
    text = _doc_text()
    named = set(_RULE_TOKEN.findall(text))
    unknown = sorted(named - set(RULE_SPECS_BY_ID))
    assert not unknown, (
        f"{COVERAGE_DOC.name} names rule identifiers that are not in the "
        f"registry: {unknown}. An identifier outside the registry is either a "
        "typo or an invented check"
    )


def test_every_registered_rule_is_named_somewhere_in_the_doc() -> None:
    text = _doc_text()
    named = set(_RULE_TOKEN.findall(text))
    missing = sorted(set(RULE_SPECS_BY_ID) - named)
    assert not missing, (
        f"registry rules absent from {COVERAGE_DOC.name}: {missing}. A rule "
        "that touches no column must still appear, in the file-level table"
    )


def test_every_advisory_code_named_in_the_doc_is_registered() -> None:
    text = _doc_text()
    named = set(_ADVISORY_TOKEN.findall(text))
    unknown = sorted(named - set(ADVISORY_CODES))
    assert not unknown, (
        f"{COVERAGE_DOC.name} names advisory codes outside ADVISORY_CODES: "
        f"{unknown}. The code space is closed; register first, then write"
    )
