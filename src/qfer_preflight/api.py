"""The supported Python surface.

Everything a Python caller needs is re-exported from the package root, so a
portal team, a filer's internal tooling or a notebook never has to import
`engine` or `report`. Those stay private and are free to move.

Three properties this surface commits to, all of them inherited from the
command line rather than reimplemented beside it:

**Fail-closed travels with the API.** `validate` returns a `Report` for input
it could not read, rather than raising and leaving the caller to decide what
an exception means about a filing. The report from an unreadable file is
never `pass`: the reader's failure is itself an error finding, and every rule
that could not run is listed in `rules_not_evaluated` with its reason. A
caller who checks `report.status is Status.PASS` therefore cannot be handed a
clean verdict for a file nothing read.

**Detection refuses rather than guesses.** A profile that cannot be
identified raises `ProfileDetectionError` naming the near misses. There is no
"best match" path, because a header one column away from a template is the
case where the wrong columns carry the most plausible values.

**No global state, no network, no import-time work.** Importing this package
reads nothing, opens nothing and imports no argument parser;
`tests/test_public_api.py` holds it to that.

Stability policy for these names is in the README, and matches the JSON
schema's: additive is a minor version, removal or retyping is major.
"""

from __future__ import annotations

import os

from . import engine
from .detect import ProfileDetectionError, detect_profile, header_bytes_of, read_header_bytes
from .engine import ValidationInputError
from .model import Advisory, Citation, Finding, NotEvaluated, Report, Rule, Severity, Status
from .profiles import PROFILES, Profile, get_profile
from .rules import all_rules, rules_for

__all__ = [
    "Advisory",
    "Citation",
    "Finding",
    "NotEvaluated",
    "Profile",
    "ProfileDetectionError",
    "Report",
    "Rule",
    "Severity",
    "Status",
    "ValidationInputError",
    "detect_profile",
    "list_profiles",
    "list_rules",
    "validate",
]

# What a report calls a filing it was handed as bytes. The command line uses
# the file's basename; bytes have no name, and inventing a plausible one
# ("filing.csv") would put a filename that never existed into a report a filer
# might forward to somebody. This is deliberately not a valid filename.
DEFAULT_BYTES_INPUT_NAME = "<bytes>"


def _resolve_profile(profile: str | Profile) -> Profile:
    if isinstance(profile, Profile):
        return profile
    try:
        return get_profile(profile)
    except KeyError as exc:
        raise ValidationInputError(str(exc)) from exc


def validate(
    source: str | os.PathLike[str] | bytes | bytearray,
    *,
    profile: str | Profile | None = None,
    input_name: str | None = None,
) -> Report:
    """Validate one filing, given a path or its bytes.

    `profile` may be a profile identifier such as `"CEC-1306B"`, a `Profile`,
    or `None` to detect it from the filing's header. Detection reads the first
    CSV record and no more, and refuses rather than guessing.

    `input_name` is what the report calls the filing. It defaults to the
    file's basename for a path, and to `"<bytes>"` for bytes, which is not a
    valid filename on purpose: a report should not carry a plausible filename
    nobody supplied.

    Raises `ProfileDetectionError` when no profile was given and none could be
    identified, and `ValidationInputError` when a named profile does not
    exist. Every other outcome is a `Report`, including the ones where nothing
    could be read.
    """
    if isinstance(source, bytes | bytearray):
        data = bytes(source)
        chosen = (
            _resolve_profile(profile)
            if profile is not None
            else detect_profile(header_bytes_of(data))
        )
        return engine.validate_bytes(
            data, chosen, input_name if input_name is not None else DEFAULT_BYTES_INPUT_NAME
        )

    path = os.fspath(source)
    chosen = (
        _resolve_profile(profile)
        if profile is not None
        else detect_profile(read_header_bytes(path))
    )
    report = engine.validate_path(path, chosen)
    if input_name is not None:
        report.input_name = input_name
    return report


def list_profiles() -> tuple[Profile, ...]:
    """Every published form this tool knows, in registry order.

    Named `list_profiles` rather than `profiles` on purpose. This package has
    a `profiles` submodule and a `rules` submodule, and exporting callables
    under those names from the package root would rebind the module
    attributes: after `import qfer_preflight`, `qfer_preflight.profiles` would
    be this function and `qfer_preflight.profiles.PROFILES` would raise. The
    proposal for this API asked for the shorter spelling; it was measured
    against the suite, broke `tests/test_detect.py` on contact, and the
    shadowing is the kind of thing that reads as a puzzling error at a
    distance from its cause. `tests/test_public_api.py` holds the submodules
    to being reachable.
    """
    return tuple(PROFILES.values())


def list_rules(profile: str | Profile | None = None) -> tuple[Rule, ...]:
    """The rule registry, bound to a profile when one is given.

    With no profile this returns every rule in the registry with its
    applicability unresolved, which is what `qfer-preflight rules` prints.
    With a profile it returns only the rules that apply to that form, bound,
    which is what `rules --profile` prints. The two differ, and the difference
    is the point: a rule that does not apply to a form is not a rule that
    passed on it.
    """
    if profile is None:
        return all_rules()
    return rules_for(_resolve_profile(profile))
