"""One rule, re-rendered from what the registry already holds.

A finding names the rule and the offending value. The filer who wants to know why the tool
said that has had two options: `rules --profile`, which prints the whole registry, and the
filer guide, which is written per form rather than per rule. Neither answers "why this rule,
and where does its text come from" in one command.

This adds no judgement and no text. Every sentence it prints was transcribed into `rules.py`
or `codes.py` already, or is produced by the engine itself:

* the verbatim quote and its locator come from the `RuleSpec`, resolved through `bind` for the
  profile asked about, because a quote and a locator can both differ per form (ADR 0007) and
  printing the raw field would show a mapping rather than the text a filer needs;
* an unevaluated rule's reason and its promotion condition are the registry's own words;
* `--value` runs `engine.check_one_cell`, so the message shown is the message the tool would
  produce, not a second account of it that agrees today.

Two absences are rendered as themselves rather than as silence, which is this project's whole
posture and the defect class it exists to make impossible:

**Published examples.** The instructions print example values for some fields. None of that
text is transcribed anywhere in this project, and ADR 0002 governs how published text enters
it: verbatim, with a locator, or not at all. So the published-example section says no example
is recorded rather than printing nothing and letting the blank read as "the instructions give
none". `tests/test_explain.py` holds that sentence to the registry, so transcribing an example
later fails the build until this renders it.

**Values a single cell cannot test.** `--value` reaches the rules that read a cell. A
structural rule reads the submission as an object and a cross-row rule reads a column down the
file, so neither can be exercised by one value, and reporting "no finding" for them would say
the value passed a check that never ran. The rule's own `tags` decide which it is, and the
vocabulary is pinned by a test so a new kind of rule cannot fall quietly into the wrong branch.
"""

from __future__ import annotations

import json
from typing import Any

from . import describe
from .engine import check_one_cell
from .model import ADVISORY_CODES, Finding
from .profiles import PROFILES, Profile, get_profile
from .rules import RULE_SPECS, RuleSpec

#: The marker the registry writes before an unevaluated rule's promotion condition. Three of
#: the four unevaluated rules carry it; QP034 states its reason without separating one out, and
#: this renders that as "none recorded separately" rather than inventing a condition for it.
_PROMOTION_MARKER = "Promotion condition"

#: A rule's primary kind, from `tags`. `codeset` is a modifier on `field` rather than a kind of
#: its own. `tests/test_explain.py` pins this set against the registry: a rule tagged with
#: something outside it would otherwise be treated as unreachable by `--value` for no stated
#: reason.
KIND_STRUCTURAL = "structural"
KIND_FIELD = "field"
KIND_CROSS_ROW = "cross-row"
RULE_KINDS = frozenset({KIND_STRUCTURAL, KIND_FIELD, KIND_CROSS_ROW})

#: Why a rule of each kind cannot be exercised by one cell.
_UNREACHABLE_BY_CELL = {
    KIND_STRUCTURAL: (
        "this is a structural rule: it reads the submission as an object, so one cell "
        "cannot exercise it"
    ),
    KIND_CROSS_ROW: (
        "this is a cross-row rule: it reads a column down the whole file, so one cell "
        "cannot exercise it"
    ),
}

_NO_PUBLISHED_EXAMPLE = (
    "No published example is recorded for this rule. The instructions print example values "
    "for some fields; none of that text is transcribed in this project, and under ADR 0002 "
    "published text is reproduced verbatim with a locator or not at all. This says so rather "
    "than printing nothing, which would read as the instructions giving no example."
)


class ExplainError(Exception):
    """The registry holds no rule or advisory code by that name."""


def rule_kind(spec: RuleSpec) -> str:
    """The rule's primary kind, from its tags.

    Raises rather than guessing. A rule whose tags name no kind is a registry error, and
    defaulting it to `field` would make `--value` report "no finding" for a rule it never ran.
    """
    kinds = [tag for tag in spec.tags if tag in RULE_KINDS]
    if len(kinds) != 1:
        raise ExplainError(
            f"rule {spec.id} carries tags {spec.tags!r}, which name "
            f"{len(kinds)} of the kinds {sorted(RULE_KINDS)}; exactly one is required"
        )
    return kinds[0]


def promotion_condition(reason: str | None) -> str | None:
    """The promotion condition an unevaluated rule states, or None where it states none."""
    if not reason:
        return None
    index = reason.find(_PROMOTION_MARKER)
    if index == -1:
        return None
    return reason[index:].strip()


def _spec(rule_id: str) -> RuleSpec:
    for spec in RULE_SPECS:
        if spec.id == rule_id:
            return spec
    raise ExplainError(
        f"no rule {rule_id!r} is registered. Rule identifiers are permanent and are never "
        f"reused, so an unknown one is unknown rather than retired; `qfer-preflight rules` "
        f"lists the {len(RULE_SPECS)} that exist."
    )


def _profiles_for(spec: RuleSpec, profile_id: str | None) -> list[Profile]:
    if profile_id is not None:
        return [get_profile(profile_id)]
    return [p for p in PROFILES.values() if spec.applies(p)]


def _binding(spec: RuleSpec, profile: Profile) -> dict[str, Any]:
    """How this rule reads on one form: its citation, and the text it was derived from."""
    if not spec.applies(profile):
        return {
            "profile": profile.id,
            "applies": False,
            "note": (
                f"{spec.id} does not apply to {profile.id}. Applicability is derived from the "
                "transcribed text rather than from a list of profile ids (ADR 0007), so this "
                "form's instructions do not carry the sentence the rule rests on."
            ),
        }
    rule = spec.bind(profile)
    return {
        "profile": profile.id,
        "applies": True,
        "citation": rule.citation.to_dict(),
        "quote": rule.quote,
    }


def _finding_payload(finding: Finding) -> dict[str, Any]:
    return {
        "rule": finding.rule_id,
        "severity": str(finding.severity),
        "column": finding.column,
        "message": finding.message,
    }


def _value_payload(spec: RuleSpec, profiles: list[Profile], value: str) -> dict[str, Any]:
    """What the engine says about this value, and what `describe.py` sees in it.

    The value is placed in each column of each form in turn and the engine's own row checks
    are run, so no mapping from rule to column is maintained here: the columns this rule reads
    are the columns it fires on. A rule that fires nowhere is reported as firing nowhere, which
    is a statement about this value rather than a verdict on it.
    """
    kind = rule_kind(spec)
    payload: dict[str, Any] = {
        "value": value,
        "shown": describe.show(value),
        "visible": describe.visible(value),
        "characters": [
            {"position": i + 1, "character": ch, "name": describe.character_name(ch)}
            for i, ch in enumerate(value)
        ],
        "cell_note": describe.cell_note(value).strip(),
        "kind": kind,
    }
    if kind != KIND_FIELD:
        payload["exercised"] = False
        payload["note"] = _UNREACHABLE_BY_CELL[kind]
        return payload

    payload["exercised"] = True
    hits: list[dict[str, Any]] = []
    for profile in profiles:
        if not spec.applies(profile):
            continue
        for column in profile.header:
            for finding in check_one_cell(profile, column, value):
                if finding.rule_id != spec.id:
                    continue
                hits.append({"profile": profile.id, **_finding_payload(finding)})
    payload["findings"] = hits
    if not hits:
        payload["note"] = (
            f"{spec.id} raised nothing for this value in any column of "
            f"{', '.join(p.id for p in profiles if spec.applies(p))}. That is what this run "
            "found, not a statement that the filing would pass: every other rule was still "
            "running against the empty cells around it."
        )
    return payload


def explain_rule(
    rule_id: str, *, profile_id: str | None = None, value: str | None = None
) -> dict[str, Any]:
    """Everything the registry holds about one rule."""
    spec = _spec(rule_id)
    profiles = _profiles_for(spec, profile_id)
    payload: dict[str, Any] = {
        "kind": "rule",
        "id": spec.id,
        "title": spec.title,
        "severity": str(spec.severity),
        "tags": list(spec.tags),
        "rule_kind": rule_kind(spec),
        "cites": spec.cites,
        "implemented": spec.implemented,
        "profiles": [_binding(spec, profile) for profile in profiles],
        "published_example": {"recorded": False, "note": _NO_PUBLISHED_EXAMPLE},
    }
    if not spec.implemented:
        payload["unevaluated"] = {
            "reason": spec.unimplemented_reason,
            "promotion_condition": promotion_condition(spec.unimplemented_reason),
        }
    if value is not None:
        payload["value"] = _value_payload(spec, profiles, value)
    return payload


def explain_advisory(code: str) -> dict[str, Any]:
    """An advisory code: what the reader noticed, and that no published rule covers it."""
    if code not in ADVISORY_CODES:
        raise ExplainError(
            f"no advisory code {code!r} is registered. The advisory code space is closed "
            f"(ADR 0004); the registered codes are {', '.join(sorted(ADVISORY_CODES))}."
        )
    return {
        "kind": "advisory",
        "code": code,
        "note": (
            f"{code} is an advisory, not a rule. It carries no severity and no citation, "
            "because no published document states the thing it reports. It says the reader "
            "noticed something the published record does not cover, and it keeps the verdict "
            "off `pass` rather than deciding the filing is wrong. The code space is closed by "
            "ADVISORY_CODES so that the advisory channel cannot become a back door for checks "
            "that could not survive as rules. See ADR 0004."
        ),
    }


def explain(
    name: str, *, profile_id: str | None = None, value: str | None = None
) -> dict[str, Any]:
    """One rule identifier or one advisory code."""
    if name.startswith("ADV-"):
        if value is not None or profile_id is not None:
            raise ExplainError(
                f"{name} is an advisory code, not a rule. It has no per-form citation and no "
                "cell-level check, so --profile and --value do not apply to it."
            )
        return explain_advisory(name)
    return explain_rule(name, profile_id=profile_id, value=value)


def _quote_lines(binding: dict[str, Any]) -> list[str]:
    if not binding["applies"]:
        return [f"### {binding['profile']}", "", binding["note"], ""]
    citation = binding["citation"]
    lines = [
        f"### {binding['profile']}",
        "",
        f"Source:   {citation['source']}",
        f"Locator:  {citation['locator']}",
        f"URL:      {citation['url']}",
    ]
    if citation.get("authority"):
        lines.append(f"Authority: {citation['authority']}")
    lines.append("")
    if binding["quote"]:
        lines += [
            "Transcribed verbatim, defects included (ADR 0002):",
            "",
            f"    {binding['quote']}",
            "",
        ]
    else:
        lines += ["No quote is transcribed for this rule on this form.", ""]
    return lines


def _unevaluated_lines(unevaluated: dict[str, Any]) -> list[str]:
    out = [
        "## Registered and not evaluated",
        "",
        "This rule is registered, reported as unevaluated on every run, and never "
        "reports as passed (ADR 0001).",
        "",
        str(unevaluated["reason"]),
        "",
        "### What would promote it",
        "",
    ]
    condition = unevaluated["promotion_condition"]
    if condition:
        out += [condition, ""]
    else:
        out += [
            "The registry states no promotion condition separately for this rule; the "
            "reason above is what it records.",
            "",
        ]
    return out


def _value_lines(value: dict[str, Any]) -> list[str]:
    out = [f"## The value {value['shown']}", ""]
    if value["characters"]:
        out += ["Character by character:", ""]
        out += [f"    {char['position']}. {char['name']}" for char in value["characters"]]
        out.append("")
    if value["cell_note"]:
        out += [value["cell_note"], ""]
    if not value["exercised"]:
        return [*out, value["note"], ""]
    for finding in value["findings"]:
        out += [
            f"{finding['profile']}, column {finding['column']}, {finding['severity']}:",
            "",
            f"    {finding['message']}",
            "",
        ]
    if not value["findings"]:
        out += [value["note"], ""]
    return out


def render_text(payload: dict[str, Any]) -> str:
    """The explanation as text. Deterministic: no clock, no set iteration."""
    if payload["kind"] == "advisory":
        return "\n".join([f"# {payload['code']}", "", payload["note"], ""])

    out = [
        f"# {payload['id']}  {payload['title']}",
        "",
        f"Severity: {payload['severity']}",
        f"Kind:     {payload['rule_kind']}"
        + (f" ({', '.join(payload['tags'])})" if payload["tags"] else ""),
        f"Cites:    {payload['cites']}",
        "",
    ]
    if not payload["implemented"]:
        out += _unevaluated_lines(payload["unevaluated"])

    out += ["## The published text", ""]
    for binding in payload["profiles"]:
        out += _quote_lines(binding)

    out += ["## Published example", "", payload["published_example"]["note"], ""]

    value = payload.get("value")
    if value is not None:
        out += _value_lines(value)
    return "\n".join(out).rstrip("\n") + "\n"


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
