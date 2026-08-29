"""Figures the README states about the code, derived from the code.

Two of them were wrong, in the two different ways a published number goes wrong.

The hostile-corpus count drifted. It read "twenty six" and was correct when written;
`tests/test_adversarial_input.py` later gained a twenty seventh case, for the fullwidth
digit convention, and the sentence was not touched. Nothing failed, because nothing read it.

The header ordinal was wrong from the first commit. The README said `NumberofCustomers` is
the seventh column of `CEC-1306A` Schedule 1. It is the eighth; the seventh is `NAICSCode`.
That sentence is this repository's justification for reproducing a published defect rather
than correcting it (ADR 0002), so a reader checking it against the CEC template landed on
the wrong cell, and the transcription convention looked wrong when it was right.

Correcting the literals would leave both able to go wrong again, so the numbers are read out
of the artifacts they describe: the case corpus, the profile headers, and the rule registry.
Each check locates its sentence by the words around it and fails if the sentence is gone,
because the figure is the reason the sentence is there.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

from qfer_preflight.profiles import PROFILE_1306A_S1, PROFILE_1306A_S2, PROFILES
from qfer_preflight.rules import RULE_SPECS

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"

NUMBER_WORDS: dict[int, str] = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}
"""Cardinals, for the counts the README spells out rather than writing in digits."""

ORDINAL_WORDS: dict[int, str] = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
}
"""Ordinals, for the column positions the README names in words."""

TENS_WORDS: dict[int, str] = {20: "twenty", 30: "thirty", 40: "forty"}


def spelled(count: int) -> str:
    """``27`` as ``"twenty seven"``, in this README's style: no hyphen, no "and".

    Only the range the README actually uses is supported. A count outside it raises here
    rather than silently comparing against nothing.
    """
    if count in NUMBER_WORDS:
        return NUMBER_WORDS[count]
    tens, units = divmod(count, 10)
    base = TENS_WORDS.get(tens * 10)
    if base is None:
        raise AssertionError(f"this test cannot spell {count}; extend the tables above")
    return base if units == 0 else f"{base} {NUMBER_WORDS[units]}"


def readme() -> str:
    # Newlines folded to spaces: these sentences wrap, and where they wrap is not a fact.
    return re.sub(r"\s+", " ", README.read_text(encoding="utf-8"))


def stated(pattern: str) -> str:
    """The one thing the README says at ``pattern``, which must match exactly once."""
    found = re.findall(pattern, readme())
    assert found, f"the README no longer states this; pattern matched nothing: {pattern}"
    assert len(found) == 1, f"pattern is ambiguous, matched {len(found)}: {pattern}"
    return str(found[0])


def adversarial_cases() -> dict[str, bytes]:
    """The hostile corpus, imported rather than parsed, so it is the corpus that runs."""
    spec = importlib.util.spec_from_file_location(
        "_adversarial_corpus", REPO / "tests" / "test_adversarial_input.py"
    )
    assert spec and spec.loader
    module: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases: dict[str, bytes] = module.CASES
    return cases


def test_the_hostile_corpus_is_the_size_the_readme_says() -> None:
    said = stated(r"attacked with ([a-z ]+?) deliberately hostile files")
    assert said == spelled(len(adversarial_cases()))


def test_the_lower_case_o_typo_is_in_the_column_the_readme_names() -> None:
    """`NumberofCustomers`, and where it actually sits in the transcribed header."""
    position = PROFILE_1306A_S1.header.index("NumberofCustomers") + 1
    said = stated(r"Schedule 1 spells its ([a-z]+) column `NumberofCustomers`")
    assert said == ORDINAL_WORDS[position]


def test_the_missing_e_typo_is_in_the_column_the_readme_names() -> None:
    position = PROFILE_1306A_S2.header.index("RetailRatClass") + 1
    said = stated(r"Schedule 2 spells its ([a-z]+) column `RetailRatClass`")
    assert said == ORDINAL_WORDS[position]


def test_both_reproduced_typos_are_still_in_the_headers_they_are_claimed_for() -> None:
    """The sentence claims two published defects are carried. If a later edit "fixes" one,
    the ordinal checks above would pass on a header that no longer has the typo in it."""
    assert "NumberofCustomers" in PROFILE_1306A_S1.header
    assert "RetailRatClass" in PROFILE_1306A_S2.header


def test_the_readme_counts_the_rules_it_leaves_unevaluated() -> None:
    unimplemented = [spec for spec in RULE_SPECS if not spec.implemented]
    said = stated(r"These ([a-z]+) are the honest half of the tool")
    assert said == spelled(len(unimplemented))


def test_every_unevaluated_rule_has_a_row_explaining_why() -> None:
    """The count above would pass if the table listed four different rules."""
    text = readme()
    for spec in RULE_SPECS:
        if not spec.implemented:
            assert f"| {spec.id} |" in text, f"{spec.id} is unevaluated and unexplained"


def test_every_registered_rule_appears_in_the_readme() -> None:
    text = readme()
    for spec in RULE_SPECS:
        assert f"| {spec.id} |" in text, f"{spec.id} is registered but never listed"


def test_the_readme_lists_every_supported_profile() -> None:
    text = readme()
    for name in PROFILES:
        assert f"`{name}`" in text, f"{name} is supported but never named"


# ---------------------------------------------------------------------------
# Which table a rule is in, not merely that it is in one.
#
# `test_every_registered_rule_appears_in_the_readme` and
# `test_every_unevaluated_rule_has_a_row_explaining_why` both look for
# `| QP0NN |` anywhere in the file. The README has two rule tables, and the
# split between them is the claim a reader acts on: the first says these
# checks run, the second says these four deliberately do not.
#
# Nothing read the split. QP005's row was moved out of the unevaluated table
# and into the implemented one, so the README told a filer that totals rows
# are checked when no rule evaluates them, and `pytest -q` reported 505
# passed. `CLAUDE.md` says never let an unevaluated rule report as passed;
# ADR 0001 makes it the repository's first contract. The engine honours it.
# The README could say the opposite and no gate objected.
#
# So the membership of both tables is derived from `implemented`.
# ---------------------------------------------------------------------------

IMPLEMENTED_TABLE_INTRO = "Implemented and grounded in published text:"
UNEVALUATED_TABLE_INTRO = "Registered but **not implemented**, and reported as unevaluated"

_RULE_ROW = re.compile(r"^\| (QP[0-9]{3}) \|", re.MULTILINE)


def _table_after(intro: str) -> str:
    """The markdown table introduced by `intro`, up to the blank line after it.

    Located by the sentence that introduces it rather than by position, so a
    reordered README fails loudly here instead of silently reading the wrong
    table.
    """
    text = README.read_text(encoding="utf-8")
    assert intro in text, f"the README no longer introduces a table with {intro!r}"
    body = text[text.index(intro) + len(intro) :]
    rows: list[str] = []
    started = False
    for line in body.splitlines():
        if line.startswith("|"):
            started = True
            rows.append(line)
        elif started:
            break
    assert rows, f"no table follows {intro!r} in the README"
    return "\n".join(rows)


def _ids_in_table(intro: str) -> set[str]:
    return set(_RULE_ROW.findall(_table_after(intro)))


def test_the_implemented_table_is_exactly_the_implemented_rules() -> None:
    listed = _ids_in_table(IMPLEMENTED_TABLE_INTRO)
    expected = {spec.id for spec in RULE_SPECS if spec.implemented}
    assert listed == expected, (
        "the README's implemented table does not match the registry. "
        f"listed but not implemented: {sorted(listed - expected)}; "
        f"implemented but not listed: {sorted(expected - listed)}. A rule shown "
        "as implemented when it is not tells a filer a check runs that does not"
    )


def test_the_unevaluated_table_is_exactly_the_unevaluated_rules() -> None:
    listed = _ids_in_table(UNEVALUATED_TABLE_INTRO)
    expected = {spec.id for spec in RULE_SPECS if not spec.implemented}
    assert listed == expected, (
        "the README's unevaluated table does not match the registry. "
        f"listed but implemented: {sorted(listed - expected)}; "
        f"unevaluated but not listed: {sorted(expected - listed)}"
    )


def test_no_rule_is_listed_in_both_tables() -> None:
    """The two assertions above cannot both hold for a rule in both tables, but
    a rule in both is worth its own message: it is the shape a careless move
    leaves behind, and the reader sees a contradiction rather than a gap."""
    both = sorted(_ids_in_table(IMPLEMENTED_TABLE_INTRO) & _ids_in_table(UNEVALUATED_TABLE_INTRO))
    assert not both, f"the README lists {both} as both implemented and unevaluated"
