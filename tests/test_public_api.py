"""The published Python surface, held to the command line it wraps.

A public API around a validator is only worth having if it is the same
validator. Two things could quietly stop being true: the API could render a
report differently from `check`, and the API could lose the fail-closed
guarantee that is the whole point of this tool. Both are asserted here
against real fixtures rather than against mocks.

The import-purity tests are here for a different reason. `import
qfer_preflight` is on the path of every consumer, including ones that import
it to read `__version__` and nothing else, so it must not drag in an argument
parser or open a file. Those are the kind of promise that is true when
written and false four commits later, so they are checked rather than
documented.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import subprocess
import sys
import types
from pathlib import Path

import pytest

import qfer_preflight
from qfer_preflight import (
    ProfileDetectionError,
    Status,
    ValidationInputError,
    detect_profile,
    list_profiles,
    list_rules,
    validate,
)
from qfer_preflight.cli import main
from qfer_preflight.detect import header_bytes_of, read_header_bytes

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"

# Fixtures whose header matches a published template, so detection succeeds and
# the API and the CLI can be compared without either being told the profile.
DETECTABLE = (
    "1306a_s1_clean.csv",
    "1306a_s1_dirty.csv",
    "1306b_clean.csv",
    "1308b_s1_clean.csv",
    "1308c_clean.csv",
)


def cli_output(argv: list[str]) -> str:
    """What `qfer-preflight` prints to stdout for these arguments."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main(argv)
    return buffer.getvalue()


@pytest.mark.parametrize("name", DETECTABLE)
@pytest.mark.parametrize(
    ("fmt", "method"),
    [("json", "to_json"), ("text", "to_text"), ("sarif", "to_sarif")],
)
def test_the_api_renders_exactly_what_the_command_line_prints(
    name: str, fmt: str, method: str
) -> None:
    """Every CLI output path is reachable through the API with identical output.

    Byte equality, not "equivalent". A JSON field ordered differently or a
    heading worded differently would mean two renderings a reader could be
    shown, and only one of them is the one the schema documents.
    """
    path = str(FIXTURES / name)
    assert getattr(validate(path), method)() == cli_output(["check", path, "--format", fmt])


def test_bytes_and_path_reach_the_same_verdict() -> None:
    """The two entrances observe one implementation.

    Only `input_name` may differ, because bytes have no name.
    """
    path = FIXTURES / "1306a_s1_dirty.csv"
    from_path = validate(str(path))
    from_bytes = validate(path.read_bytes())
    assert from_bytes.input_sha256 == from_path.input_sha256
    assert from_bytes.status is from_path.status
    assert from_bytes.rows_read == from_path.rows_read
    assert [f.rule_id for f in from_bytes.findings] == [f.rule_id for f in from_path.findings]


def test_empty_bytes_digest_matches_the_command_line_on_an_empty_file() -> None:
    """`validate(b"")` and `check empty.csv` are the same run over the same bytes."""
    empty = FIXTURES / "empty.csv"
    assert empty.read_bytes() == b"", "the empty fixture is no longer empty"
    report = validate(b"", profile="CEC-1306B")
    assert report.input_sha256 == hashlib.sha256(b"").hexdigest()
    from_cli = validate(str(empty), profile="CEC-1306B")
    assert report.input_sha256 == from_cli.input_sha256


def test_an_unreadable_filing_returns_a_report_and_never_reads_as_clean() -> None:
    """Fail-closed travels with the API.

    The issue proposing this surface expected `UNVALIDATED` here. What the
    engine actually produces for unreadable bytes is `FAIL`, because the
    reader's own failure is an error finding, and `FAIL` is the louder of the
    two. The guarantee worth asserting is the one that holds either way: a
    `Report` comes back rather than an exception, the verdict is not `PASS`,
    and no rule is claimed to have been evaluated successfully over content
    nothing could read.
    """
    report = validate(b"\xff\xfe\x00 not utf-8 at all", profile="CEC-1306B")
    assert report.status is not Status.PASS
    assert report.rules_not_evaluated, "a filing nothing read reported no unevaluated rules"
    assert report.findings, "a filing nothing read produced no findings"


def test_detection_refuses_rather_than_choosing_a_near_miss() -> None:
    """A header close to a template is refused, and the near misses are advice.

    This is the assertion that stops a future "just pick the best match"
    convenience from being added: the refusal names candidates precisely so
    that nothing has to guess, and the candidates must not become a fallback.
    """
    header = read_header_bytes(str(FIXTURES / "wrong_header.csv"))
    with pytest.raises(ProfileDetectionError) as caught:
        detect_profile(header)
    error = caught.value
    assert error.reason == "no_match"
    assert error.near_misses, "a refusal that lists nothing helps nobody"
    known = {profile.id for profile in list_profiles()}
    assert set(error.near_misses) <= known


def test_an_empty_filing_is_refused_as_empty_not_as_a_mismatch() -> None:
    """Zero rows and a wrong header are different problems and say so."""
    with pytest.raises(ProfileDetectionError) as caught:
        detect_profile(b"")
    assert caught.value.reason == "empty"


def test_an_undecodable_header_is_refused_as_unreadable() -> None:
    with pytest.raises(ProfileDetectionError) as caught:
        detect_profile(b"\xff\xfe\x00\x01")
    assert caught.value.reason == "unreadable"


def test_an_unknown_profile_name_is_a_typed_input_error() -> None:
    with pytest.raises(ValidationInputError):
        validate(b"", profile="CEC-9999")


def test_header_detection_reads_the_first_record_and_no_more() -> None:
    """A bad byte in row nine thousand is not a fact about the header.

    `header_bytes_of` must stop at the first line break, so a filing whose
    header is fine and whose body is not still detects.
    """
    good = (FIXTURES / "1306b_clean.csv").read_bytes()
    header = good.split(b"\n", 1)[0].rstrip(b"\r")
    assert header_bytes_of(good + b"\n\xff\xfe rubbish") == header
    assert detect_profile(header_bytes_of(good)).id == "CEC-1306B"


def test_the_registry_the_api_publishes_is_the_registry_the_cli_prints() -> None:
    """`list_rules()` and `rules --format json` list the same identifiers.

    Both call `rules.all_rules`, so this fails only if somebody gives one of
    them a second implementation.
    """
    from_cli = cli_output(["rules", "--format", "json"])
    for rule in list_rules():
        assert f'"{rule.id}"' in from_cli


def test_a_profile_narrows_the_registry_rather_than_passing_everything() -> None:
    """A rule that does not apply to a form is absent, not silently passed."""
    everything = {rule.id for rule in list_rules()}
    for profile in list_profiles():
        bound = {rule.id for rule in list_rules(profile.id)}
        assert bound <= everything
        assert bound, f"{profile.id} has no applicable rules at all"
    narrowed = {rule.id for rule in list_rules("CEC-1306B")}
    assert narrowed < everything, "no profile narrows the registry; applicability is inert"


def test_no_exported_name_shadows_a_submodule() -> None:
    """A public callable must not take a submodule's attribute slot.

    Exporting `profiles()` and `rules()` from the package root does exactly
    that: `from .api import profiles` rebinds `qfer_preflight.profiles` from
    the module to the function, so `qfer_preflight.profiles.PROFILES` stops
    resolving. That is why the accessors are `list_profiles` and `list_rules`
    rather than the shorter names the proposal asked for. This is the guard,
    because the failure appears far from its cause: an AttributeError inside
    somebody else's monkeypatch, months later.
    """
    package = Path(qfer_preflight.__file__).parent
    submodules = {path.stem for path in package.glob("*.py") if path.stem != "__init__"}
    collisions = sorted(submodules & set(qfer_preflight.__all__))
    assert not collisions, (
        f"{collisions} are both submodules and exported names, so the exported "
        "object hides the module"
    )
    for name in submodules:
        attribute = getattr(qfer_preflight, name, None)
        if attribute is not None:
            assert isinstance(attribute, types.ModuleType), (
                f"qfer_preflight.{name} is a {type(attribute).__name__}, not the submodule"
            )


def test_every_public_name_exists_and_is_exported() -> None:
    for name in qfer_preflight.__all__:
        assert hasattr(qfer_preflight, name), f"{name} is in __all__ and not defined"
    for name in ("validate", "detect_profile", "list_profiles", "list_rules", "Report", "Status"):
        assert name in qfer_preflight.__all__


# Reading a module's own source or bytecode is the import system doing its job,
# and every import does it. Those are filtered out so that what is left is what
# the claim is actually about: a data file, a config file, a cache. This
# project publishes code sets and template headers, and the tempting way to
# ship one is to load it from disk at import; that is what this catches.
IMPORT_PURITY_PROBE = """
import sys

opened = []


def hook(event, args):
    if event in ("open", "os.open"):
        path = str(args[0])
        if not path.endswith((".py", ".pyc", ".pth")):
            opened.append(path)


sys.addaudithook(hook)
import qfer_preflight  # noqa: E402

assert qfer_preflight.__version__
print("ARGPARSE", "argparse" in sys.modules)
print("OPENED", opened)
"""


def _probe_import() -> tuple[str, str]:
    finished = subprocess.run(
        [sys.executable, "-c", IMPORT_PURITY_PROBE],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(REPO),
    )
    lines = dict(line.split(" ", 1) for line in finished.stdout.strip().splitlines())
    return lines["ARGPARSE"], lines["OPENED"]


def test_importing_the_package_does_not_import_an_argument_parser() -> None:
    """A library consumer should not pay for the command line.

    Run in a subprocess with a fresh interpreter, because this test module has
    already imported `cli` and would otherwise assert about its own imports.
    """
    argparse_seen, _ = _probe_import()
    assert argparse_seen == "False"


def test_importing_the_package_does_not_open_a_data_file() -> None:
    """No config read, no code set loaded from disk, no cache written, at import.

    Checked with an audit hook rather than by inspection, so a file opened
    deep inside a submodule is caught too. Module source and bytecode are
    excluded by the probe: reading those is the import system, not the
    package. What is left is exactly the thing worth forbidding here, because
    the published code sets and template headers this project ships would be
    easy to load from a data file, and a library that reads the filesystem at
    import is one a caller cannot vendor or run from a zipapp.
    """
    _, opened = _probe_import()
    assert opened == "[]", f"importing qfer_preflight opened data files: {opened}"
