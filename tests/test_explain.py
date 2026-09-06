"""`qfer-preflight explain`: one rule, re-rendered from the registry.

The verb adds no text. That makes it easy to test tautologically, and a tautological test here
would be worse than none: reading the quote out of `RULE_SPECS` and asserting the output
contains the quote out of `RULE_SPECS` passes for any renderer that echoes its input, and
passes just as well after the registry is edited to say something wrong.

So the acceptance cases below pin the literal strings the issue names: the county the published
table records for `7`, the locator that points at rule 6 of the workshop deck, the sentence
that says why a padded county is a warning. If the registry ever stops supporting one of them,
that is exactly the moment a person should be made to look, and these fail rather than quietly
following the registry to a new answer.

The structural cases derive instead, because there the property is about every rule rather than
one: that every registered identifier explains without raising, that the tag vocabulary the
`--value` path branches on is the vocabulary the registry actually uses, and that a rule one
cell cannot exercise says so rather than reporting that nothing was found.
"""

from __future__ import annotations

import json

import pytest

from qfer_preflight import cli
from qfer_preflight.cli import EXIT_OK, EXIT_USAGE
from qfer_preflight.explain import (
    RULE_KINDS,
    ExplainError,
    explain,
    promotion_condition,
    render_json,
    render_text,
    rule_kind,
)
from qfer_preflight.model import ADVISORY_CODES
from qfer_preflight.profiles import PROFILES
from qfer_preflight.rules import RULE_SPECS


def run(*argv: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# The three acceptance cases from the issue, pinned to literal published text.
# ---------------------------------------------------------------------------


def test_explaining_a_padded_county_prints_the_table_entry_and_why_it_is_a_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`explain QP024 --value 07`, the issue's worked example.

    Three separate claims, each pinned to the literal text rather than to whatever the registry
    currently holds: the county the published table records for `7`, the locator naming rule 6
    of the workshop deck, and the engine's own sentence saying why this is a warning.
    """
    code, out, _ = run("explain", "QP024", "--value", "07", capsys=capsys)
    assert code == EXIT_OK

    # The county table entry.
    assert "Contra Costa" in out
    assert "The published county table writes it '7'" in out

    # The workshop deck, rule 6.
    assert 'slide 19, "Formatting Rules (3/3)", rule 6' in out
    assert (
        "Any Company Number, County Number, and NAICS code values that contain a "
        "leading 0 (zero) should be formatted as TEXT data type." in out
    )

    # Why the severity is what it is.
    assert "Severity: warning" in out
    assert (
        "No published source calls the padded form an error, so this is reported as a "
        "warning rather than a failure." in out
    )


def test_explaining_an_unevaluated_rule_prints_its_reason_and_promotion_condition(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`explain QP018`. The reason and the condition are the registry's words; that the
    condition is *declined* rather than pending is the fact ADR 0009 settled."""
    code, out, _ = run("explain", "QP018", capsys=capsys)
    assert code == EXIT_OK
    assert "Registered and not evaluated" in out
    assert "never reports as passed" in out
    assert "match the list of Valid NAICS codes" in out
    assert "What would promote it" in out
    assert "Promotion condition" in out
    assert "not expected to be met" in out
    assert "ADR 0009" in out


def test_an_unknown_rule_exits_2_and_names_no_rule(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run("explain", "QP999", capsys=capsys)
    assert code == EXIT_USAGE
    assert out == ""
    assert "QP999" in err
    # It must not offer a rule it does invent or guess at.
    assert not any(spec.id in err for spec in RULE_SPECS)


# ---------------------------------------------------------------------------
# Absence rendered as itself.
# ---------------------------------------------------------------------------


def test_a_rule_no_single_cell_can_exercise_says_so_rather_than_finding_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A structural rule read against one value must not report "no finding".

    Reporting nothing would say the value passed a check that never ran, which is the defect
    this project exists to make impossible.
    """
    code, out, _ = run("explain", "QP001", "--value", "abc", capsys=capsys)
    assert code == EXIT_OK
    assert "one cell cannot exercise it" in out
    assert "structural rule" in out


def test_a_cross_row_rule_says_it_reads_the_file_rather_than_a_cell(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = run("explain", "QP030", "--value", "7", capsys=capsys)
    assert code == EXIT_OK
    assert "cross-row rule" in out
    assert "one cell cannot exercise it" in out


def test_a_field_rule_that_fires_nowhere_says_that_and_claims_no_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A value that raises nothing is reported as raising nothing, not as passing."""
    code, out, _ = run("explain", "QP024", "--value", "7", capsys=capsys)
    assert code == EXIT_OK
    assert "raised nothing for this value" in out
    assert "not a statement that the filing would pass" in out


def test_the_missing_published_example_is_stated_rather_than_left_blank(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No published example text is transcribed in this project. The output must say that.

    If an example is ever transcribed, this fails until `explain` renders it, which is the
    point: a blank section would read as the instructions printing no example.
    """
    code, out, _ = run("explain", "QP013", capsys=capsys)
    assert code == EXIT_OK
    assert "Published example" in out
    assert "No published example is recorded for this rule" in out
    assert "ADR 0002" in out


def test_a_rule_with_no_transcribed_quote_says_so_rather_than_showing_a_gap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """QP002 rests on the published template's header row, not on a sentence, so no quote is
    transcribed for it. The citation still resolves, and the missing quote must be named.

    A blank where the quote goes would read as a rule with nothing behind it, which is the
    opposite of true here: the citation points at the template itself.
    """
    code, out, _ = run("explain", "QP002", "--profile", "CEC-1306A-S1", capsys=capsys)
    assert code == EXIT_OK
    assert "No quote is transcribed for this rule on this form." in out
    # The citation is still shown; the absence is of the quote, not of the source.
    assert "URL:" in out


def test_the_no_quote_case_is_a_case_this_registry_actually_has() -> None:
    """The assertion above would pass over nothing if every rule carried a quote."""
    from qfer_preflight.profiles import PROFILES as _PROFILES

    quoteless = [
        (spec.id, profile_id)
        for spec in RULE_SPECS
        for profile_id, profile in _PROFILES.items()
        if spec.applies(profile) and spec.bind(profile).quote is None
    ]
    assert quoteless, (
        "every registered rule now carries a quote on every form it applies to, so the "
        "no-quote rendering is unreachable and the test above proves nothing"
    )


def test_a_rule_that_does_not_apply_to_a_form_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--profile` naming a form the rule does not reach must not print an empty citation."""
    spec_by_id = {spec.id: spec for spec in RULE_SPECS}
    pairs = [
        (spec_id, profile_id)
        for spec_id, spec in spec_by_id.items()
        for profile_id, profile in PROFILES.items()
        if not spec.applies(profile)
    ]
    assert pairs, "no rule fails to apply to some profile; this test would prove nothing"
    spec_id, profile_id = pairs[0]
    code, out, _ = run("explain", spec_id, "--profile", profile_id, capsys=capsys)
    assert code == EXIT_OK
    assert f"{spec_id} does not apply to {profile_id}" in out
    assert "URL:" not in out


def test_a_rule_that_does_not_apply_says_it_never_ran_against_the_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--profile` and `--value` together must not report a run that never happened.

    `_binding` reports non applicability as its own fact. `_value_payload` did
    not: it set `exercised` true, ran nothing, and printed

        QPnnn raised nothing for this value in any column of .

    naming an empty list of forms and reading exactly like a rule that ran
    across every column and found the value clean. That is the same misreading
    `test_a_rule_no_single_cell_can_exercise_says_so_rather_than_finding_nothing`
    exists to prevent for a structural rule.
    """
    spec_by_id = {spec.id: spec for spec in RULE_SPECS}
    pairs = [
        (spec_id, profile_id)
        for spec_id, spec in spec_by_id.items()
        for profile_id, profile in PROFILES.items()
        if not spec.applies(profile) and rule_kind(spec) == "field"
    ]
    assert pairs, "no field rule fails to apply to some profile; this test would prove nothing"
    spec_id, profile_id = pairs[0]

    payload = explain(spec_id, profile_id=profile_id, value="XYZ")
    assert payload["value"]["exercised"] is False
    assert "was not run against this value" in payload["value"]["note"]
    assert profile_id in payload["value"]["note"]

    code, out, _ = run("explain", spec_id, "--profile", profile_id, "--value", "XYZ", capsys=capsys)
    assert code == EXIT_OK
    assert "was not run against this value" in out
    assert "raised nothing for this value" not in out
    assert "in any column of ." not in out


# ---------------------------------------------------------------------------
# Properties over the whole registry.
# ---------------------------------------------------------------------------


def test_every_registered_rule_explains_without_raising() -> None:
    assert len(RULE_SPECS) == 28, (
        f"the registry holds {len(RULE_SPECS)} rules; this sweep is written against 28, and a "
        "count that has moved means the loops below may be covering less than they did"
    )
    for spec in RULE_SPECS:
        payload = explain(spec.id)
        assert payload["id"] == spec.id
        assert render_text(payload)
        json.loads(render_json(payload))


def test_every_advisory_code_explains_without_raising() -> None:
    assert len(ADVISORY_CODES) == 5, (
        f"the advisory code space holds {len(ADVISORY_CODES)} codes; this sweep expects 5"
    )
    for code in ADVISORY_CODES:
        payload = explain(code)
        assert payload["code"] == code
        assert "no published document states" in render_text(payload)


def test_the_kind_vocabulary_is_the_one_the_registry_uses() -> None:
    """`--value` branches on the rule's kind. A tag outside this vocabulary would be sorted
    into the wrong branch silently, so the branch and the registry are held together."""
    used = {tag for spec in RULE_SPECS for tag in spec.tags}
    unaccounted = used - RULE_KINDS - {"codeset"}
    assert not unaccounted, (
        f"the registry tags rules {sorted(unaccounted)}, which `explain` does not know how to "
        "treat; either they are a new kind or they are a modifier like `codeset`"
    )
    for spec in RULE_SPECS:
        assert rule_kind(spec) in RULE_KINDS


def test_every_unevaluated_rule_states_its_reason() -> None:
    unevaluated = [spec for spec in RULE_SPECS if not spec.implemented]
    assert len(unevaluated) == 4, (
        f"{len(unevaluated)} rules are registered unevaluated; this expects 4"
    )
    for spec in unevaluated:
        payload = explain(spec.id)
        assert payload["unevaluated"]["reason"], f"{spec.id} is unevaluated with no reason"


def test_the_promotion_condition_reader_actually_finds_the_conditions() -> None:
    """A parser that matched nothing would report "none recorded" for every rule and look
    like a clean pass. This pins how many it must find."""
    found = [
        spec.id
        for spec in RULE_SPECS
        if not spec.implemented and promotion_condition(spec.unimplemented_reason)
    ]
    assert sorted(found) == ["QP005", "QP018", "QP032"], (
        f"the promotion-condition reader found {sorted(found)}; three of the four unevaluated "
        "rules state one, and QP034 states its reason without separating a condition out"
    )
    # And the one that states none is rendered as stating none, not as a blank.
    payload = explain("QP034")
    assert payload["unevaluated"]["promotion_condition"] is None
    assert "states no promotion condition separately" in render_text(payload)


def test_output_is_byte_identical_across_runs() -> None:
    for args in (("QP024",), ("QP018",), ("ADV-BOM",)):
        first = render_text(explain(*args))
        second = render_text(explain(*args))
        assert first == second
    payload = explain("QP024", profile_id="CEC-1306A-S1", value="07")
    assert render_json(payload) == render_json(
        explain("QP024", profile_id="CEC-1306A-S1", value="07")
    )


def test_the_json_rendering_carries_the_same_facts_as_the_text() -> None:
    payload = explain("QP024", profile_id="CEC-1306A-S1", value="07")
    data = json.loads(render_json(payload))
    assert data["severity"] == "warning"
    assert data["rule_kind"] == "field"
    assert data["value"]["exercised"] is True
    assert any("Contra Costa" in f["message"] for f in data["value"]["findings"])


# ---------------------------------------------------------------------------
# Refusals.
# ---------------------------------------------------------------------------


def test_an_unknown_advisory_code_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run("explain", "ADV-NOPE", capsys=capsys)
    assert code == EXIT_USAGE
    assert "closed" in err


def test_an_advisory_takes_no_profile_or_value(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run("explain", "ADV-BOM", "--value", "07", capsys=capsys)
    assert code == EXIT_USAGE
    assert "not a rule" in err


def test_an_unknown_profile_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run("explain", "QP024", "--profile", "NOPE", capsys=capsys)
    assert code == EXIT_USAGE
    assert "NOPE" in err


def test_a_rule_whose_tags_name_no_kind_is_refused_rather_than_assumed() -> None:
    """`rule_kind` must not default. Defaulting to `field` would make `--value` report "no
    finding" for a rule whose check it never ran."""
    from dataclasses import replace

    spec = replace(RULE_SPECS[0], tags=("codeset",))
    with pytest.raises(ExplainError, match="exactly one is required"):
        rule_kind(spec)
