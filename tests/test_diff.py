"""`qfer-preflight diff`: what changed between two runs over one filing.

A filer runs the check, edits the spreadsheet, exports again and re-runs. The
verb answers "what changed" without saying anything the two reports do not
already say.

These tests hold three things: the comparison is right, it refuses what it
cannot compare rather than producing a number nobody should read, and it cannot
pass over nothing. The last is the one that needs saying out loud: almost every
assertion here looks for a list with particular contents, and a diff that found
no difference at all would satisfy several of them.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
from typing import Any

import pytest

from qfer_preflight.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main
from qfer_preflight.diff import (
    CHANGED,
    NEW,
    RESOLVED,
    UNCHANGED,
    NotComparable,
    diff_reports,
    load_report,
    new_error_appeared,
    to_text,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _run_json(path: str) -> str:
    """`check --format json` over one fixture, captured."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main(["check", path, "--format", "json"])
    return buffer.getvalue()


def _checked(csv_name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(_run_json(str(FIXTURES / csv_name)))
    return document


@pytest.fixture
def dirty() -> dict[str, Any]:
    return _checked("1306a_s1_dirty.csv")


@pytest.fixture
def clean() -> dict[str, Any]:
    return _checked("1306a_s1_clean.csv")


# --- the comparison ----------------------------------------------------------


def test_a_report_against_itself_is_entirely_unchanged(dirty: dict[str, Any]) -> None:
    diff = diff_reports(dirty, copy.deepcopy(dirty))
    assert diff["findings"], "the dirty fixture reports findings; comparing it found none"
    assert {e["status"] for e in diff["findings"]} == {UNCHANGED}
    assert not new_error_appeared(diff)


def test_the_dirty_report_against_the_clean_one_resolves_everything_and_adds_nothing(
    dirty: dict[str, Any], clean: dict[str, Any]
) -> None:
    diff = diff_reports(dirty, clean)
    statuses = [e["status"] for e in diff["findings"]]
    assert statuses, "no findings were compared at all"
    assert set(statuses) == {RESOLVED}
    assert len(statuses) == len(dirty["findings"])
    assert not new_error_appeared(diff)


def test_the_clean_report_against_the_dirty_one_is_the_mirror(
    dirty: dict[str, Any], clean: dict[str, Any]
) -> None:
    """The control for the test above: if `_compare` reported everything as
    resolved whatever it was given, that test would pass over a broken diff."""
    diff = diff_reports(clean, dirty)
    assert {e["status"] for e in diff["findings"]} == {NEW}
    assert new_error_appeared(diff), "eleven error findings appeared and none was called new"


def test_a_finding_that_moved_rows_is_a_count_change_not_a_new_problem(
    dirty: dict[str, Any],
) -> None:
    """A filer who fixed row 4 and reintroduced the same problem at row 900 has
    the same published rule failing on the same column with the same message.
    Reporting that as resolved-and-new would tell them they had introduced a
    problem they already had."""
    after = copy.deepcopy(dirty)
    target = next(f for f in after["findings"] if f.get("column"))
    target["row"] = (target.get("row") or 2) + 900
    diff = diff_reports(dirty, after)
    moved = [e for e in diff["findings"] if e["status"] == CHANGED]
    assert len(moved) == 1, [e["status"] for e in diff["findings"]]
    assert moved[0]["before"]["rows"] != moved[0]["after"]["rows"]
    assert RESOLVED not in {e["status"] for e in diff["findings"]}
    assert NEW not in {e["status"] for e in diff["findings"]}
    assert not new_error_appeared(diff)


def test_a_rising_occurrence_count_is_stated_as_a_count_change(dirty: dict[str, Any]) -> None:
    after = copy.deepcopy(dirty)
    target = after["findings"][0]
    target["occurrences"] = target.get("occurrences", 1) + 40
    target.setdefault("example_rows", [target.get("row", 2)])
    diff = diff_reports(dirty, after)
    entry = next(e for e in diff["findings"] if e["status"] == CHANGED)
    assert entry["after"]["occurrences"] > entry["before"]["occurrences"]
    assert "count" in to_text(diff)


def test_advisories_and_unevaluated_rules_are_diffed_the_same_way(dirty: dict[str, Any]) -> None:
    assert dirty["rules_not_evaluated"], "the fixture no longer exercises this list"
    after = copy.deepcopy(dirty)
    dropped = after["rules_not_evaluated"].pop()
    diff = diff_reports(dirty, after)
    resolved = [e for e in diff["rules_not_evaluated"] if e["status"] == RESOLVED]
    assert [e["key"][0] for e in resolved] == [dropped["rule_id"]]


# --- what it refuses ---------------------------------------------------------


def test_two_profiles_are_refused_with_the_reason(dirty: dict[str, Any]) -> None:
    other = copy.deepcopy(dirty)
    other["profile"] = {"id": "CEC-1306B", "title": "Another form"}
    with pytest.raises(NotComparable, match="different profiles"):
        diff_reports(dirty, other)


def test_a_foreign_schema_version_is_refused(dirty: dict[str, Any]) -> None:
    other = copy.deepcopy(dirty)
    other["schema_version"] = 99
    with pytest.raises(NotComparable, match="schema version"):
        diff_reports(dirty, other)


def test_a_batch_envelope_is_refused_by_name(tmp_path: Path) -> None:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main(
            [
                "check",
                str(FIXTURES / "1306a_s1_dirty.csv"),
                str(FIXTURES / "1306a_s1_clean.csv"),
                "--format",
                "json",
            ]
        )
    envelope = tmp_path / "batch.json"
    envelope.write_text(buffer.getvalue(), encoding="utf-8")
    with pytest.raises(NotComparable, match="batch envelope"):
        load_report(envelope)


def test_a_file_that_is_not_a_report_is_refused(tmp_path: Path) -> None:
    for name, body in (("empty.json", ""), ("list.json", "[]"), ("other.json", '{"a": 1}')):
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        with pytest.raises(NotComparable):
            load_report(path)


# --- exit codes --------------------------------------------------------------


def _write(tmp_path: Path, name: str, document: dict[str, Any]) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def test_exit_zero_when_nothing_is_new(
    tmp_path: Path, dirty: dict[str, Any], clean: dict[str, Any]
) -> None:
    before = _write(tmp_path, "before.json", dirty)
    after = _write(tmp_path, "after.json", clean)
    assert main(["diff", before, after]) == EXIT_OK


def test_exit_one_when_a_new_error_appeared(
    tmp_path: Path, dirty: dict[str, Any], clean: dict[str, Any]
) -> None:
    before = _write(tmp_path, "before.json", clean)
    after = _write(tmp_path, "after.json", dirty)
    assert main(["diff", before, after]) == EXIT_FINDINGS


def test_exit_two_when_they_cannot_be_compared(tmp_path: Path, dirty: dict[str, Any]) -> None:
    other = copy.deepcopy(dirty)
    other["profile"] = {"id": "CEC-1306B", "title": "Another form"}
    before = _write(tmp_path, "before.json", dirty)
    after = _write(tmp_path, "after.json", other)
    assert main(["diff", before, after]) == EXIT_USAGE


def test_json_output_is_parseable_and_deterministic(
    tmp_path: Path, dirty: dict[str, Any], clean: dict[str, Any], capsys: Any
) -> None:
    before = _write(tmp_path, "before.json", dirty)
    after = _write(tmp_path, "after.json", clean)
    main(["diff", before, after, "--format", "json"])
    first = capsys.readouterr().out
    main(["diff", before, after, "--format", "json"])
    second = capsys.readouterr().out
    assert first == second
    parsed = json.loads(first)
    assert parsed["profile"]["id"] == dirty["profile"]["id"]
    assert parsed["before"]["input"]["sha256"] == dirty["input"]["sha256"]
    assert parsed["after"]["input"]["sha256"] == clean["input"]["sha256"]


# --- the checks that keep the checks honest ----------------------------------


def test_the_header_names_both_runs(dirty: dict[str, Any], clean: dict[str, Any]) -> None:
    text = to_text(diff_reports(dirty, clean))
    for document in (dirty, clean):
        assert document["input"]["name"] in text
        assert document["input"]["sha256"][:12] in text
        assert document["tool_version"] in text


def test_every_difference_the_structure_records_reaches_the_printed_text(
    dirty: dict[str, Any], clean: dict[str, Any]
) -> None:
    """A section counted in the summary and printed nowhere is a difference
    reported as nothing having happened. That is the failure this tool exists to
    refuse one level down, and it is available here too."""
    diff = diff_reports(dirty, clean)
    text = to_text(diff)
    for section in ("findings", "advisories", "rules_not_evaluated"):
        for entry in diff[section]:
            assert entry["key"][0] in text, f"{section} entry {entry['key']} is not in the text"


def test_the_comparison_can_actually_report_a_difference(
    dirty: dict[str, Any], clean: dict[str, Any]
) -> None:
    """The floor. Every assertion above about an empty list would be satisfied by
    a diff that never reported anything, so one is required to report something."""
    diff = diff_reports(dirty, clean)
    assert any(e["status"] != UNCHANGED for e in diff["findings"])
    assert "  resolved " in to_text(diff), "no line was rendered as resolved"
    same = diff_reports(dirty, copy.deepcopy(dirty))
    assert all(e["status"] == UNCHANGED for e in same["findings"])
    # The summary line always spells the word ("0 resolved"), so the control has
    # to look for a rendered entry rather than the word anywhere in the output.
    assert "  resolved " not in to_text(same)


def test_the_advisory_section_is_actually_exercised(dirty: dict[str, Any]) -> None:
    """The 1306A-S1 dirty fixture raises no advisory, so the "every difference
    reaches the text" test above passes over an empty advisory list. This gives
    it one, because a section that is never rendered in any test is a section
    whose rendering nothing checks."""
    after = copy.deepcopy(dirty)
    after["advisories"] = [
        {
            "code": "ADV-BOM",
            "message": "The file begins with a UTF-8 byte order mark; no published rule covers it.",
            "column": "",
        }
    ]
    diff = diff_reports(dirty, after)
    assert [e["status"] for e in diff["advisories"]] == [NEW]
    text = to_text(diff)
    assert "Advisories:" in text
    assert "ADV-BOM" in text
    assert "advisories: 0 resolved, 1 new" in text


def test_two_silent_reports_say_so_rather_than_printing_an_empty_page(
    clean: dict[str, Any],
) -> None:
    """Both runs reported nothing. An empty findings section reads as a page
    that failed to render; the text says which it is."""
    empty = copy.deepcopy(clean)
    empty["rules_not_evaluated"] = []
    diff = diff_reports(empty, copy.deepcopy(empty))
    text = to_text(diff)
    assert "nothing to compare" in text


def test_an_unreadable_path_is_refused_rather_than_treated_as_empty(tmp_path: Path) -> None:
    missing = tmp_path / "there-is-no-such-file.json"
    with pytest.raises(NotComparable, match="cannot be read"):
        load_report(missing)


def test_a_repeated_finding_prints_its_row_count(dirty: dict[str, Any]) -> None:
    after = copy.deepcopy(dirty)
    after["findings"] = []
    before = copy.deepcopy(dirty)
    target = before["findings"][0]
    target["occurrences"] = 12
    target["example_rows"] = [2, 3, 4, 5, 6, 7, 8]
    target["last_row"] = 40
    text = to_text(diff_reports(before, after))
    assert "12 rows," in text
    assert "rows 2, 3, 4, 5, 6" in text and "…" in text
