"""What `docs/ROADMAP.md` claims about this tree, derived from the tree.

The roadmap described Phases 1 and 2 as forward work after they were built. Nothing in it
carried a state, so a reader arriving at "### 2.2 Batch mode" read a plan, and issues #33 to
#40 were filed for work that was already shipped. That is the defect #45 records.

Prose alone cannot fix it. A status hand-written beside each item is another figure nothing
re-derives, and this repository has already measured what happens to those: the README said
the hostile corpus held "twenty six" files, a twenty seventh landed, and the sentence stayed
wrong until `tests/test_readme_claims.py` started reading it out of the corpus.

The roadmap was in exactly that state when this test was written. Four of its figures had
drifted, and one of them disagreed with the same document three hundred lines later:

    "Twenty-three implemented rules"                  -- the registry holds 24
    "three registered as permanently unevaluated"     -- there are 4; QP034 was missing
    "an adversarial corpus of twenty six hostile"     -- the corpus holds 27
    "Nine ADRs recording the decisions"               -- there are 10, and Phase 6 of this
                                                         same file already said "The ten
                                                         that exist"

So both halves are read out of the tree here. A status is a claim about the code, and every
`shipped` claim must name evidence that exists; every figure is compared against the artifact
it describes.

Two things this file is deliberate about.

`stated()` requires its pattern to match exactly **once**. A presence check cannot catch a
document that says the same thing twice and disagrees with itself, which is the "Nine ADRs"
defect above. Matching twice is a failure here, not a pass.

`test_the_status_sweep_reads_every_phase_heading` exists because every assertion below is a
loop over parsed items, and a parser that silently matches nothing makes all of them vacuous.
It pins the heading count so a heading that stops being read is a failure rather than a
quietly smaller loop.
"""

from __future__ import annotations

import importlib.util
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qfer_preflight.profiles import PROFILES
from qfer_preflight.rules import RULE_SPECS

REPO = Path(__file__).resolve().parent.parent
ROADMAP = REPO / "docs" / "ROADMAP.md"
ADR_DIR = REPO / "docs" / "adr"

#: The two states a roadmap item may claim. `shipped` is checkable against the tree and must
#: name its evidence; `continuing` is growth work with no end state, so it names none.
STATUSES = frozenset({"shipped", "continuing"})

#: Phase headings, the only headings that carry a state. `## Phase N: ...` and `### N.M ...`.
_PHASE_HEADING = re.compile(r"^(?P<hashes>##|###) (?P<title>Phase [0-9]+:.*|[0-9]+\.[0-9]+ .*)$")

_STATUS_LINE = re.compile(r"^\*\*Status: (?P<status>[a-z]+)\.\*\*(?P<rest>.*)$")

#: A sequencing-table row: order, work with its phase reference, then the status cell.
_SEQUENCING_ROW = re.compile(
    r"^\| *(?P<order>[0-9]+) *\| *(?P<work>[^|]*?)\((?P<refs>[0-9., ]+)\) *\| *"
    r"(?P<status>[a-z]+) *\|"
)

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
TENS_WORDS: dict[int, str] = {20: "twenty", 30: "thirty", 40: "forty"}


def spelled(count: int) -> str:
    """``27`` as ``"twenty seven"``. Hyphens are normalised away by `stated()`."""
    if count in NUMBER_WORDS:
        return NUMBER_WORDS[count]
    tens, units = divmod(count, 10)
    base = TENS_WORDS.get(tens * 10)
    if base is None:
        raise AssertionError(f"this test cannot spell {count}; extend the tables above")
    return base if units == 0 else f"{base} {NUMBER_WORDS[units]}"


def roadmap() -> str:
    """Newlines folded to spaces, and hyphens in spelled numbers folded to spaces too.

    Where a sentence wraps is not a fact, and neither is whether this document writes
    "twenty-four" or "twenty four"; both are the same claim about the registry.
    """
    text = ROADMAP.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", text.replace("-", " "))


def stated(pattern: str) -> str:
    """The one thing the roadmap says at ``pattern``, which must match exactly once.

    Exactly once, not at least once. A second match is a second copy of the same claim, and
    an uncontrolled second copy is how "Nine ADRs" survived beside "The ten that exist".
    """
    found = re.findall(pattern, roadmap())
    assert found, f"the roadmap no longer states this; pattern matched nothing: {pattern}"
    assert len(found) == 1, (
        f"pattern matched {len(found)} times, so this document states the same thing more "
        f"than once and nothing holds the copies together: {pattern}"
    )
    return str(found[0])


@dataclass(frozen=True)
class Item:
    """One roadmap phase heading and the state it claims."""

    heading: str
    status: str
    evidence: tuple[str, ...]


def items() -> tuple[Item, ...]:
    """Every phase heading, with the status marker that follows it."""
    parsed: list[Item] = []
    heading: str | None = None
    status: str | None = None
    evidence: tuple[str, ...] = ()

    def flush() -> None:
        nonlocal heading, status, evidence
        if heading is not None:
            assert status is not None, f"{heading} carries no `**Status:**` marker"
            parsed.append(Item(heading, status, evidence))
        heading, status, evidence = None, None, ()

    for line in ROADMAP.read_text(encoding="utf-8").splitlines():
        match = _PHASE_HEADING.match(line)
        if match:
            flush()
            heading = match.group("title").strip()
            continue
        if line.startswith("## ") or line.startswith("### "):
            flush()
            continue
        marker = _STATUS_LINE.match(line)
        if marker and heading is not None:
            assert status is None, f"{heading} carries two `**Status:**` markers"
            status = marker.group("status")
            evidence = tuple(re.findall(r"`([^`]+)`", marker.group("rest")))
    flush()
    return tuple(parsed)


def adr_decisions() -> tuple[Path, ...]:
    """The ADRs that record a decision.

    `0000-record-architecture-decisions.md` is the decision to keep ADRs at all, not one of
    the decisions that constrain the code, so it is not counted among them.
    """
    return tuple(
        sorted(p for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md") if p.name[:4] != "0000")
    )


def adversarial_cases() -> dict[str, bytes]:
    """The hostile corpus, imported rather than parsed, so it is the corpus that runs."""
    spec = importlib.util.spec_from_file_location(
        "_roadmap_adversarial_corpus", REPO / "tests" / "test_adversarial_input.py"
    )
    assert spec and spec.loader
    module: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases: dict[str, bytes] = module.CASES
    return cases


# ---------------------------------------------------------------------------
# The status markers, and that they are read at all.
# ---------------------------------------------------------------------------


def test_the_status_sweep_reads_every_phase_heading() -> None:
    """Every assertion below loops over `items()`. If the parser stopped matching, they would
    all pass over an empty list. This pins what it must find."""
    headings = [i.heading for i in items()]
    phases = [h for h in headings if h.startswith("Phase ")]
    sub_items = [h for h in headings if not h.startswith("Phase ")]
    assert len(phases) == 6, f"six phases are documented; the sweep found {phases}"
    assert len(sub_items) == 8, (
        f"Phases 1 and 2 hold eight numbered items between them; the sweep found {sub_items}"
    )


def test_every_phase_item_claims_a_state_from_the_closed_vocabulary() -> None:
    for item in items():
        assert item.status in STATUSES, (
            f"{item.heading} claims the state {item.status!r}, which is not one of "
            f"{sorted(STATUSES)}; an unknown state is checked by nothing"
        )


def test_every_shipped_claim_names_evidence_that_exists() -> None:
    """A status is a claim about the code. `shipped` beside an item whose files are not there
    is the roadmap's original defect wearing the fix's clothes."""
    by_heading = {i.heading: i for i in items()}
    for item in items():
        if item.status != "shipped":
            continue
        if item.heading.startswith("Phase "):
            # A phase heading states the state of the items beneath it, which carry the
            # evidence themselves; `test_a_shipped_phase_has_only_shipped_items_under_it`
            # is what holds it to them.
            number = item.heading.split()[1].rstrip(":")
            if any(h.startswith(f"{number}.") for h in by_heading):
                continue
        assert item.evidence, f"{item.heading} claims shipped and names no evidence"
        for reference in item.evidence:
            path_part, _, symbol = reference.partition("::")
            path = REPO / path_part
            assert path.exists(), (
                f"{item.heading} claims shipped on the evidence of {path_part}, "
                f"which is not in the tree"
            )
            if symbol:
                body = path.read_text(encoding="utf-8")
                assert symbol in body, (
                    f"{item.heading} claims shipped on the evidence of {symbol} in "
                    f"{path_part}, which does not appear there"
                )


def test_continuing_work_claims_no_evidence() -> None:
    """`continuing` means there is no state to reach. An item that names evidence is claiming
    one, and should say `shipped` so the evidence is checked."""
    for item in items():
        if item.status == "continuing":
            assert not item.evidence, (
                f"{item.heading} is continuing yet names evidence {item.evidence}; "
                "either it is shipped, or the evidence does not belong there"
            )


def test_a_shipped_phase_has_only_shipped_items_under_it() -> None:
    """Phase 1 and Phase 2 claim shipped on behalf of their numbered items. That is a
    derivation, so it is derived rather than trusted."""
    by_heading = {i.heading: i for i in items()}
    for item in items():
        if not item.heading.startswith("Phase ") or item.status != "shipped":
            continue
        number = item.heading.split()[1].rstrip(":")
        children = [i for h, i in by_heading.items() if h.startswith(f"{number}.")]
        assert children, f"{item.heading} claims shipped with no numbered items beneath it"
        unshipped = [i.heading for i in children if i.status != "shipped"]
        assert not unshipped, (
            f"{item.heading} claims shipped, but these items under it do not: {unshipped}"
        )


def test_the_sequencing_table_agrees_with_every_item_it_points_at() -> None:
    """The table states each item's state a second time. Two statements of one fact are safe
    only while something holds them together; this is that."""
    by_heading = {i.heading: i for i in items()}
    rows = 0
    for line in ROADMAP.read_text(encoding="utf-8").splitlines():
        row = _SEQUENCING_ROW.match(line)
        if not row:
            continue
        rows += 1
        assert row.group("status") in STATUSES, (
            f"sequencing row {row.group('order')} claims {row.group('status')!r}"
        )
        for ref in (r.strip() for r in row.group("refs").split(",")):
            heading = next(
                (h for h in by_heading if h.startswith(f"{ref} ") or h.startswith(f"Phase {ref}:")),
                None,
            )
            assert heading is not None, (
                f"sequencing row {row.group('order')} points at ({ref}), which is not a "
                "heading in this document"
            )
            assert by_heading[heading].status == row.group("status"), (
                f"sequencing row {row.group('order')} says ({ref}) is "
                f"{row.group('status')!r}; the item itself says "
                f"{by_heading[heading].status!r}"
            )
    assert rows == 10, f"the sequencing table has ten rows; the sweep read {rows}"


# ---------------------------------------------------------------------------
# The figures. Each is read out of the artifact it describes.
# ---------------------------------------------------------------------------


def test_the_roadmap_counts_the_rules_the_registry_implements() -> None:
    implemented = [spec for spec in RULE_SPECS if spec.implemented]
    said = stated(r"([A-Za-z ]+?) implemented rules and")
    assert said.strip().lower() == spelled(len(implemented))


def test_the_roadmap_counts_the_rules_it_leaves_unevaluated() -> None:
    unimplemented = [spec for spec in RULE_SPECS if not spec.implemented]
    said = stated(r"implemented rules and ([a-z]+) registered as permanently")
    assert said == spelled(len(unimplemented))


def test_the_roadmap_names_every_unevaluated_rule_it_counts() -> None:
    """The count above would pass while the parenthesis listed the wrong rules. QP034 was
    unevaluated and unnamed there for exactly as long as nothing read this."""
    text = roadmap()
    listed = stated(r"unevaluated so far \(([^)]*)\)")
    for spec in RULE_SPECS:
        if not spec.implemented:
            assert spec.id in listed, (
                f"{spec.id} is registered unevaluated and is not named in the roadmap's list"
            )
    named = set(re.findall(r"QP[0-9]{3}", listed))
    actual = {spec.id for spec in RULE_SPECS if not spec.implemented}
    assert named == actual, f"the roadmap lists {sorted(named)}; the registry has {sorted(actual)}"
    assert text  # the document was read


def test_the_roadmap_counts_the_hostile_corpus_where_it_describes_the_engine() -> None:
    said = stated(r"an adversarial corpus of ([a-z ]+?) hostile files")
    assert said.strip() == spelled(len(adversarial_cases()))


def test_the_roadmap_counts_the_hostile_corpus_where_it_plans_to_grow_it() -> None:
    """The same number, in a different sentence three hundred lines away. Phase 5 said
    "Twenty six cases exist" while the engine paragraph said the same thing; both were stale,
    and a check reading only one of them would have called the document fixed."""
    said = stated(r"Adversarial corpus growth\. ([A-Za-z ]+?) cases exist")
    assert said.strip().lower() == spelled(len(adversarial_cases()))


def test_no_other_sentence_states_a_different_corpus_size() -> None:
    """The two checks above each read one sentence. Neither would notice a third sentence
    inventing a third number, which is the shape the defect had in the first place."""
    truth = spelled(len(adversarial_cases()))
    claims = re.findall(r"([A-Za-z]+(?: [a-z]+)?) (?:hostile files|cases exist)", roadmap())
    assert claims, "no sentence in the roadmap states the corpus size any more"
    wrong = [c for c in claims if c.strip().lower() != truth]  # case is not part of the claim
    assert not wrong, (
        f"the corpus holds {len(adversarial_cases())} cases ({truth}); these sentences say "
        f"otherwise: {wrong}"
    )


def test_the_roadmap_counts_the_adrs_that_record_a_decision() -> None:
    said = stated(r"([A-Za-z]+) ADRs recording the decisions")
    assert said.lower() == spelled(len(adr_decisions()))


def test_phase_six_counts_the_same_adrs() -> None:
    """ "Nine ADRs recording the decisions" and "The ten that exist" stood in one document,
    three hundred lines apart, and the second was right."""
    said = stated(r"The ([a-z]+) that exist are why the guardrails")
    assert said == spelled(len(adr_decisions()))


def test_the_roadmap_counts_the_profiles_the_package_supports() -> None:
    said = stated(r"([A-Za-z]+) form profiles, their headers transcribed")
    assert said.lower() == spelled(len(PROFILES))


def test_the_roadmap_states_the_coverage_floor_the_gate_enforces() -> None:
    """A floor stated in prose and a floor enforced in `pyproject.toml` are two figures. This
    is the one that would let the document promise 90 while the gate accepted less."""
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    floor = int(config["tool"]["coverage"]["report"]["fail_under"])
    said = stated(r"tests with a ([0-9]+)\s*percent coverage floor")
    assert int(said) == floor
