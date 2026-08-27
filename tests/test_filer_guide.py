"""The filer guide and the glossary stay true to the tool they describe.

`docs/filer-guide.md` makes two kinds of claim a reader would act on: that a
block of CSV is a valid example of a published form, and that running the tool
on it produces a particular status, a particular set of unevaluated rules and
a particular exit code. Both can rot silently. A rule added to the registry
changes the counts; a template transcription corrected in `profiles.py`
changes the header; a severity moved changes the exit code.

So the guide is not read here as prose. Every example is extracted, written to
disk, and run through the same entry point a filer's run uses, and its stated
outcome is compared against the real one. A guide that says something the tool
does not do fails the suite.

The glossary is held to the narrower claim it makes: that the code set values
it names are the ones `codes.py` carries.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from qfer_preflight.cli import EXIT_FINDINGS, EXIT_OK, main
from qfer_preflight.codes import GAS_CUSTOMER_GROUPS, VALID_UDC_VALUES
from qfer_preflight.engine import validate_path
from qfer_preflight.model import ADVISORY_CODES, Status
from qfer_preflight.profiles import PROFILES, detect_profiles
from qfer_preflight.report import to_text
from qfer_preflight.rules import RULE_SPECS_BY_ID

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "filer-guide.md"
GLOSSARY = ROOT / "docs" / "glossary.md"

_RULE_TOKEN = re.compile(r"\bQP[0-9]{3}\b")
_ADVISORY_TOKEN = re.compile(r"\bADV-[A-Z]+(?:-[A-Z]+)*\b")

# "Reported: status UNVALIDATED, 19 rules evaluated, 4 not evaluated (QP005,
# QP018, QP032, QP034), 0 advisories, exit code 0."
_REPORTED = re.compile(
    r"Reported: status ([A-Z]+), ([0-9]+) rules evaluated, "
    r"([0-9]+) not evaluated \(([^)]*)\), ([0-9]+) advisories, "
    r"exit code ([0-9]+)\.",
    re.DOTALL,
)


class Example:
    """One CSV block from the guide, with the outcome the guide claims for it."""

    def __init__(self, heading: str, csv_text: str, claim: re.Match[str]) -> None:
        self.heading = heading
        self.csv_text = csv_text
        self.status = claim.group(1)
        self.evaluated = int(claim.group(2))
        self.not_evaluated_count = int(claim.group(3))
        self.not_evaluated = tuple(
            token for token in _RULE_TOKEN.findall(claim.group(4).replace("\n", " "))
        )
        self.advisories = int(claim.group(5))
        self.exit_code = int(claim.group(6))

    def __repr__(self) -> str:  # pragma: no cover
        return f"Example({self.heading!r})"


def _guide_text() -> str:
    assert GUIDE.exists(), f"{GUIDE} is missing"
    return GUIDE.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Collapse whitespace, so a prose assertion is not defeated by a line wrap."""
    return re.sub(r"\s+", " ", text)


def _glossary_text() -> str:
    assert GLOSSARY.exists(), f"{GLOSSARY} is missing"
    return GLOSSARY.read_text(encoding="utf-8")


def _examples() -> list[Example]:
    """Every ```csv block in the guide, with its heading and its stated outcome.

    A block without a `Reported:` line following it is a failure rather than a
    skip: an example whose outcome is not stated is an example nothing holds.
    """
    text = _guide_text()
    lines = text.splitlines()
    found: list[Example] = []
    heading = ""
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
        if line.strip() == "```csv":
            body: list[str] = []
            index += 1
            while index < len(lines) and lines[index].strip() != "```":
                body.append(lines[index])
                index += 1
            rest = "\n".join(lines[index : index + 12])
            claim = _REPORTED.search(rest)
            assert claim is not None, (
                f"the example under {heading!r} states no outcome. Every CSV "
                "block in the guide needs a 'Reported: ...' line within a few "
                "lines of it, so a real run can be compared against it"
            )
            found.append(Example(heading, "\n".join(body) + "\n", claim))
        index += 1
    assert found, "no CSV examples found in the filer guide"
    return found


def _write(tmp_path: Path, example: Example, name: str) -> Path:
    path = tmp_path / name
    path.write_text(example.csv_text, encoding="utf-8")
    return path


def test_every_profile_has_a_section_in_the_guide() -> None:
    text = _guide_text()
    missing = [pid for pid in PROFILES if f"### {pid}" not in text]
    assert not missing, (
        f"{GUIDE.name} has no section for {missing}. Every published profile "
        "gets a page, so a new form cannot ship without one"
    )


def test_every_example_header_is_a_published_header() -> None:
    """An example whose header is not a transcribed template is a wrong example."""
    for example in _examples():
        header = tuple(example.csv_text.splitlines()[0].split(","))
        matches = detect_profiles(header)
        assert len(matches) == 1, (
            f"the example under {example.heading!r} has header {header}, which "
            f"matches {len(matches)} published templates. Examples are copied "
            "from the transcribed headers, typos included"
        )


def test_profile_sections_show_their_own_form() -> None:
    for example in _examples():
        if example.heading not in PROFILES:
            continue
        header = tuple(example.csv_text.splitlines()[0].split(","))
        assert detect_profiles(header)[0].id == example.heading, (
            f"the example under {example.heading!r} is a different form's header"
        )


def test_examples_report_what_the_guide_says(tmp_path: Path) -> None:
    for number, example in enumerate(_examples()):
        path = _write(tmp_path, example, f"example-{number}.csv")
        profile = detect_profiles(tuple(example.csv_text.splitlines()[0].split(",")))[0]
        report = validate_path(str(path), profile)

        assert report.status.value.upper() == example.status, (
            f"{example.heading!r}: the guide says status {example.status}, the "
            f"tool reports {report.status.value.upper()}"
        )
        assert len(report.rules_evaluated) == example.evaluated, (
            f"{example.heading!r}: the guide says {example.evaluated} rules "
            f"evaluated, the tool evaluated {len(report.rules_evaluated)}"
        )
        unevaluated = tuple(item.rule_id for item in report.rules_not_evaluated)
        assert unevaluated == example.not_evaluated, (
            f"{example.heading!r}: the guide names {example.not_evaluated} as "
            f"unevaluated, the tool reports {unevaluated}"
        )
        assert len(unevaluated) == example.not_evaluated_count, (
            f"{example.heading!r}: the guide's unevaluated count and its list "
            "disagree with each other"
        )
        assert len(report.advisories) == example.advisories, (
            f"{example.heading!r}: the guide says {example.advisories} "
            f"advisories, the tool raised {len(report.advisories)}"
        )


def test_examples_exit_with_the_code_the_guide_states(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exit code is the claim a pipeline acts on, so it is checked through the CLI."""
    for number, example in enumerate(_examples()):
        path = _write(tmp_path, example, f"exit-{number}.csv")
        code = main(["check", str(path)])
        capsys.readouterr()
        assert code == example.exit_code, (
            f"{example.heading!r}: the guide says exit code "
            f"{example.exit_code}, the CLI returned {code}"
        )
        assert code in (EXIT_OK, EXIT_FINDINGS)


def _quoted_output_lines() -> list[str]:
    """Every line the guide shows inside a ```text block, as output it claims to quote."""
    lines = _guide_text().splitlines()
    quoted: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index].strip() == "```text":
            index += 1
            while index < len(lines) and lines[index].strip() != "```":
                if lines[index].strip():
                    quoted.append(_flat(lines[index]).strip())
                index += 1
        index += 1
    return quoted


def test_the_quoted_findings_are_really_what_the_tool_prints(tmp_path: Path) -> None:
    """Lines the guide shows as output are checked as quotes, not read as prose.

    A guide that paraphrases a message into something friendlier is a guide
    that will eventually paraphrase it into something untrue. Every line shown
    must be the opening of a line the tool actually emits, character for
    character up to where the excerpt stops.
    """
    failing = [example for example in _examples() if example.status == "FAIL"]
    assert failing, "the guide shows no failing run, so a filer never sees what one looks like"

    path = _write(tmp_path, failing[0], "failing.csv")
    profile = detect_profiles(tuple(failing[0].csv_text.splitlines()[0].split(",")))[0]
    printed = [
        _flat(line).strip() for line in to_text(validate_path(str(path), profile)).splitlines()
    ]

    quoted = _quoted_output_lines()
    assert quoted, "the guide quotes no output at all"
    for line in quoted:
        assert any(actual.startswith(line) for actual in printed), (
            f"{GUIDE.name} shows a finding the tool does not print:\n  {line}\n"
            "Every quoted line must be the opening of a real one"
        )


def test_the_guide_claims_strict_fails_on_a_well_formed_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guide says --strict fails on every file. Hold it to that.

    It is the guide's strongest claim about the tool and the easiest one to
    make wrong later: implementing any one of the four unevaluated rules on a
    form would make it false for that form.
    """
    text = _flat(_guide_text())
    assert "`--strict` fails on every file, always" in text

    for number, example in enumerate(_examples()):
        path = _write(tmp_path, example, f"strict-{number}.csv")
        code = main(["check", str(path), "--strict"])
        capsys.readouterr()
        assert code == EXIT_FINDINGS, (
            f"{example.heading!r}: the guide says --strict fails on every "
            f"file, but this one exited {code}"
        )


def test_every_status_the_guide_names_exists() -> None:
    named = {example.status for example in _examples()}
    known = {status.value.upper() for status in Status}
    unknown = sorted(named - known)
    assert not unknown, f"{GUIDE.name} names statuses the model does not have: {unknown}"


@pytest.mark.parametrize("doc", [GUIDE, GLOSSARY])
def test_documents_name_only_real_rule_identifiers(doc: Path) -> None:
    """Prose is where an invented check would enter, so nothing is taken on trust."""
    text = doc.read_text(encoding="utf-8")
    unknown = sorted(set(_RULE_TOKEN.findall(text)) - set(RULE_SPECS_BY_ID))
    assert not unknown, (
        f"{doc.name} names rule identifiers that are not in the registry: "
        f"{unknown}. An identifier outside the registry is either a typo or an "
        "invented check"
    )


@pytest.mark.parametrize("doc", [GUIDE, GLOSSARY])
def test_documents_name_only_registered_advisory_codes(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    unknown = sorted(set(_ADVISORY_TOKEN.findall(text)) - set(ADVISORY_CODES))
    assert not unknown, (
        f"{doc.name} names advisory codes outside ADVISORY_CODES: {unknown}. "
        "The code space is closed; register first, then write"
    )


def test_the_guide_labels_its_examples_synthetic() -> None:
    """Examples must never read as a real submission."""
    text = _flat(_guide_text())
    assert "Every example below is synthetic." in text
    assert "no row is drawn from any real filing" in text


def test_the_guide_does_not_claim_the_portal_will_accept_anything() -> None:
    text = _flat(_guide_text()).lower()
    assert "authoritative validator" in text
    assert "not affiliated with, endorsed by" in text


def test_glossary_defines_the_terms_the_sources_use() -> None:
    text = _glossary_text()
    for term in ("QFER", "DSP", "UDC", "LSE", "TEOR", "UEG", "NAICS"):
        assert f"### {term}" in text, f"{GLOSSARY.name} has no entry for {term}"


def test_glossary_defines_the_terms_the_tool_uses() -> None:
    text = _glossary_text()
    for term in ("Rule", "Finding", "Severity", "Advisory", "Unevaluated rule"):
        assert f"### {term}" in text, f"{GLOSSARY.name} has no entry for {term}"


def test_glossary_code_set_values_are_the_published_ones() -> None:
    """A glossary that describes a value `codes.py` does not carry is fiction."""
    text = _glossary_text()
    for value in ("TEOR", "UEG"):
        assert value in GAS_CUSTOMER_GROUPS
        assert value in text
    for value in sorted(VALID_UDC_VALUES):
        assert value in text, (
            f"{GLOSSARY.name} describes the UDC column but omits {value}, "
            "which is one of the published values"
        )


def test_glossary_lists_the_whole_closed_advisory_code_space() -> None:
    """The closed code space is a claim; if a code is added, the glossary must say so."""
    text = _glossary_text()
    missing = sorted(code for code in ADVISORY_CODES if code not in text)
    assert not missing, (
        f"{GLOSSARY.name} says the advisory code space is closed but does not list {missing}"
    )
