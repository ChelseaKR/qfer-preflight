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
from qfer_preflight.profiles import PROFILES, Profile
from qfer_preflight.rules import RULE_SPECS, RULE_SPECS_BY_ID

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


# ---------------------------------------------------------------------------
# The map as a derived claim, not only as a well formed one.
#
# The three assertions above hold the document's edges: the columns are the
# published ones, every identifier is real, and no rule is left off the page.
# None of them reads a cell. So the map could say that QP014 checks the
# NumberOfCustomers column of CEC-1306B, a form that has no CustomerType
# column and to which QP014 does not bind, and the suite stayed green. It was
# green: the claim was inserted, `pytest -q` reported 505 passed, and nothing
# named the cell.
#
# That is this repository's own failure mode written into prose. The map's
# stated purpose is that "the space between checks is visible instead of
# silent", and a cell naming a rule the tool will not run on that form is the
# space between checks made invisible again, in the one document written to
# show it.
#
# So the cells are now derived. For every profile, what the map names must be
# exactly what the registry binds to that profile, no more and no less. The
# document is prose and stays prose, with its reading notes and its ADR
# pointers; what is checked is the part of it that is a computation.
# ---------------------------------------------------------------------------

FILE_LEVEL_HEADING = "Checks that hold the file together"


def _section_lines(text: str, heading: str) -> list[str]:
    """The lines under one `##` heading, up to the next one."""
    lines = text.splitlines()
    collected: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == heading
            continue
        if inside:
            collected.append(line)
    assert inside or collected, f"no '## {heading}' section in {COVERAGE_DOC.name}"
    return collected


def _table_rows(lines: list[str]) -> list[list[str]]:
    """Body rows of the markdown tables in these lines, as lists of cells.

    Header rows and separator rows are dropped. Prose is ignored, which is the
    point: a rule named in a paragraph explaining that it does not apply must
    not be read as a claim that it does. That distinction is why this parses
    cells rather than scanning the section for identifiers.
    """
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells[0] in ("Column", "Rule") or set(cells[0]) <= {"-", " ", ":"}:
            continue
        rows.append(cells)
    return rows


def _file_level_rows() -> list[list[str]]:
    rows = _table_rows(_section_lines(_doc_text(), FILE_LEVEL_HEADING))
    assert rows, f"{COVERAGE_DOC.name} has no file level table, so this check would be vacuous"
    return rows


def _rules_in_column_cells(profile_id: str) -> set[str]:
    rows = _table_rows(_section_lines(_doc_text(), profile_id))
    assert rows, f"{COVERAGE_DOC.name} has no column table for {profile_id}"
    named: set[str] = set()
    for cells in rows:
        named |= set(_RULE_TOKEN.findall(" ".join(cells[1:])))
    return named


def _bound_to(profile: Profile) -> set[str]:
    """Every registered rule the registry binds to this profile."""
    return {spec.id for spec in RULE_SPECS if spec.applies(profile)}


def test_the_file_level_table_and_the_column_tables_do_not_overlap() -> None:
    """A rule is either about the file or about a column, and the map must pick.

    Without this, a field rule could be parked in the file level table, where
    no column names it, and the per column check below would never miss it.
    """
    file_level = {cells[0] for cells in _file_level_rows()}
    for profile_id in PROFILES:
        overlap = sorted(file_level & _rules_in_column_cells(profile_id))
        assert not overlap, (
            f"{overlap} appear both in the file level table and in the "
            f"{profile_id} column table. A rule listed in both is a rule whose "
            "column mapping nothing checks"
        )


def test_every_rule_the_registry_binds_to_a_profile_is_mapped_for_that_profile() -> None:
    """Per profile, not repo wide.

    `test_every_registered_rule_is_named_somewhere_in_the_doc` is satisfied by
    one mention anywhere. This one is not: a rule that binds to CEC-1308C must
    be named on CEC-1308C's own page, or in the file level table if it applies
    there too.
    """
    file_level = {cells[0] for cells in _file_level_rows()}
    for profile_id, profile in PROFILES.items():
        mapped = _rules_in_column_cells(profile_id) | {
            rule_id for rule_id in file_level if RULE_SPECS_BY_ID[rule_id].applies(profile)
        }
        bound = _bound_to(profile)
        missing = sorted(bound - mapped)
        assert not missing, (
            f"{COVERAGE_DOC.name} does not map {missing} for {profile_id}, but "
            "the registry binds them to that form. A rule that runs and is not "
            "on the map is a check the reader cannot see"
        )


def test_the_map_never_claims_a_rule_the_registry_does_not_run_on_that_form() -> None:
    """The direction that matters most, and the one that was open.

    A cell naming a rule that does not bind to the form tells a filer a column
    is checked when it is not. That is the failure `CLAUDE.md` forbids, reached
    through prose instead of through the engine.
    """
    for profile_id, profile in PROFILES.items():
        bound = _bound_to(profile)
        claimed = sorted(_rules_in_column_cells(profile_id) - bound)
        assert not claimed, (
            f"{COVERAGE_DOC.name} maps {claimed} on {profile_id}, but the "
            "registry does not bind them to that form. The map would tell a "
            "filer those columns are checked when nothing checks them"
        )


def test_the_file_level_table_states_each_rule_s_real_evaluation_state() -> None:
    """`evaluated` and `unevaluated` are read off `implemented`, never typed.

    An unevaluated rule shown as evaluated is the same untruth as an
    unevaluated rule reporting as passed, which ADR 0001 forbids.
    """
    for cells in _file_level_rows():
        rule_id, _, state = cells[0], cells[1], cells[2]
        spec = RULE_SPECS_BY_ID[rule_id]
        expected = "evaluated" if spec.implemented else "unevaluated"
        assert state.split(",")[0].strip() == expected, (
            f"{COVERAGE_DOC.name} calls {rule_id} {state.split(',')[0].strip()!r}, "
            f"but the registry has implemented={spec.implemented}"
        )


def test_a_file_level_rule_that_applies_to_some_forms_names_exactly_those_forms() -> None:
    """QP007 is the case: two forms publish the text, three do not (ADR 0007).

    A rule that applies everywhere must carry no qualifier, and a rule that
    does not must name every form it applies to and no form it does not.
    """
    for cells in _file_level_rows():
        rule_id, state = cells[0], cells[2]
        spec = RULE_SPECS_BY_ID[rule_id]
        applies = {pid for pid, profile in PROFILES.items() if spec.applies(profile)}
        if applies == set(PROFILES):
            assert "only" not in state, (
                f"{COVERAGE_DOC.name} narrows {rule_id} to {state!r}, but the "
                "registry binds it to every profile"
            )
            continue
        for profile_id in PROFILES:
            named = profile_id in state
            assert named == (profile_id in applies), (
                f"{COVERAGE_DOC.name} says {rule_id} is {state!r}. The registry "
                f"binds it to {sorted(applies)}, so naming {profile_id} there is "
                f"{'missing' if profile_id in applies else 'wrong'}"
            )
