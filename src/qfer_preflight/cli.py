"""Command line interface.

Exit codes:
  0  no error-level findings
  1  at least one error-level finding, or, with --strict, anything the tool
     could not reach a verdict on: a rule that was not evaluated, or an
     advisory the reader raised
  2  the tool was asked for something it could not do
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .engine import TOOL_NAME, validate_path
from .model import BatchEntry, Status
from .profiles import PROFILES, QFER_PROGRAM_URL, Profile, detect_profiles, get_profile
from .report import (
    batch_to_json,
    batch_to_text,
    rules_to_json,
    rules_to_text,
    to_json,
    to_text,
)
from .rules import RULE_SPECS, rules_for

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

_EPILOG = (
    "qfer-preflight runs entirely on your machine. It opens no network "
    "connection, keeps no account and sends no telemetry.\n"
    "It is an independent utility. It is not affiliated with, endorsed by or "
    "approved by the California Energy Commission.\n"
    f"Program page for the forms it reads: {QFER_PROGRAM_URL}"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qfer-preflight",
        description=(
            "Offline pre-submission validator for California Energy "
            "Commission QFER Consumption CSV filings."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate a CSV submission")
    check.add_argument(
        "paths",
        nargs="+",
        help=(
            "path to the CSV file to validate, or several of them, or "
            "directories, whose files are validated in name order"
        ),
    )
    check.add_argument(
        "--profile",
        help=(
            "form profile, for example CEC-1306A-S1. Omitted, it is detected "
            "from the file's header row, and only an exact match against one "
            "published template is accepted"
        ),
    )
    check.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    check.add_argument(
        "--strict",
        action="store_true",
        help=(
            "also exit non-zero when any rule could not be evaluated or the "
            "reader raised an advisory"
        ),
    )

    rules = sub.add_parser("rules", help="list the rule registry with citations")
    rules.add_argument("--profile", help="limit to the rules that apply to one profile")
    rules.add_argument("--format", choices=("text", "json"), default="text", help="output format")

    sub.add_parser("profiles", help="list the supported form profiles")
    return parser


def _detect_profile(path: str) -> tuple[Profile | None, str | None]:
    """Read the file's header row and match it against the published templates.

    Returns the one matching profile, or a refusal explaining why detection
    declined to guess. Detection reads the header only; it never validates, and
    a BOM stripped here is still reported by the validation run as ADV-BOM.
    """
    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            header = next(csv.reader(handle), None)
    except OSError as exc:
        return None, f"could not read {path}: {exc}"
    except (UnicodeDecodeError, csv.Error):
        return None, (
            f"could not detect a profile for {path}: its first row could not "
            "be read as UTF-8 CSV. Pass --profile explicitly to have the "
            "report say what is wrong with it"
        )
    if not header:
        return None, (
            f"could not detect a profile for {path}: the file has no rows. "
            "Pass --profile explicitly"
        )
    matches = detect_profiles(header)
    if not matches:
        return None, (
            f"could not detect a profile for {path}: its header does not "
            "match any published template byte for byte. Pass --profile "
            "explicitly"
        )
    if len(matches) > 1:
        ids = ", ".join(sorted(p.id for p in matches))
        return None, (
            f"could not detect a profile for {path}: its header matches "
            f"several templates ({ids}). Pass --profile explicitly"
        )
    return matches[0], None


def _expand_inputs(paths: Sequence[str]) -> tuple[list[str] | None, str | None]:
    """Directories become their files, in name order; everything else passes through."""
    expanded: list[str] = []
    for path in paths:
        if os.path.isdir(path):
            inside = sorted(str(item) for item in Path(path).iterdir() if item.is_file())
            if not inside:
                return None, f"no files found in {path}"
            expanded.extend(inside)
        else:
            expanded.append(path)
    if len(set(expanded)) != len(expanded):
        seen: set[str] = set()
        deduped = []
        for path in expanded:
            if path not in seen:
                deduped.append(path)
                seen.add(path)
        expanded = deduped
    return expanded, None


def _validate_one(path: str, profile: Profile | None) -> BatchEntry:
    """Validate a single input for the batch, never raising.

    Every refusal becomes an entry that says what happened, because in a batch
    one unreadable file must not take the whole run down and must not be
    silently skipped either.
    """
    chosen: Profile | None = profile
    if chosen is None:
        detected, problem = _detect_profile(path)
        if detected is None:
            return BatchEntry(input_name=path, problem=problem or "profile detection failed")
        chosen = detected
    try:
        return BatchEntry(input_name=path, report=validate_path(path, chosen))
    except OSError as exc:
        return BatchEntry(input_name=path, problem=f"could not read {path}: {exc}")


def _cmd_check(args: argparse.Namespace) -> int:
    # Exactly one named file keeps the single-document output exactly as
    # published, whatever it is: an existing filing, or a path that fails to
    # open and reports its refusal on stderr as before. Anything else,
    # including several paths and directories, produces the batch envelope.
    single_request = len(args.paths) == 1 and not os.path.isdir(args.paths[0])
    inputs, problem = _expand_inputs(args.paths)
    if problem is not None or inputs is None:
        print(problem or "no inputs", file=sys.stderr)
        return EXIT_USAGE

    if single_request:
        return _check_single(inputs[0], args)
    return _check_batch(inputs, args)


def _resolve_profile(args: argparse.Namespace) -> tuple[Profile | None, str | None]:
    if args.profile:
        try:
            return get_profile(args.profile), None
        except KeyError as exc:
            return None, str(exc)
    return None, None


def _check_single(path: str, args: argparse.Namespace) -> int:
    profile, problem = _resolve_profile(args)
    if problem is not None:
        print(problem, file=sys.stderr)
        return EXIT_USAGE
    entry = _validate_one(path, profile)
    if entry.report is None:
        # Reachable when --profile was omitted and detection refused the
        # header: single-file mode reports that refusal on stderr, exactly as
        # detection did before batch mode existed.
        print(entry.problem or "could not validate the input", file=sys.stderr)
        return EXIT_USAGE

    output = to_json(entry.report) if args.format == "json" else to_text(entry.report)
    sys.stdout.write(output)

    report = entry.report
    if report.status is Status.FAIL:
        return EXIT_FINDINGS
    if args.strict and report.status is Status.UNVALIDATED:
        return EXIT_FINDINGS
    return EXIT_OK


def _check_batch(paths: Sequence[str], args: argparse.Namespace) -> int:
    profile, problem = _resolve_profile(args)
    if problem is not None:
        print(problem, file=sys.stderr)
        return EXIT_USAGE

    entries = [_validate_one(path, profile) for path in paths]

    output = (
        batch_to_json(entries, TOOL_NAME, __version__)
        if args.format == "json"
        else batch_to_text(entries, TOOL_NAME)
    )
    sys.stdout.write(output)

    statuses = [entry.report.status for entry in entries if entry.report is not None]
    had_findings = any(
        status is Status.FAIL or (args.strict and status is Status.UNVALIDATED)
        for status in statuses
    )
    if had_findings:
        return EXIT_FINDINGS
    if any(entry.problem is not None for entry in entries):
        return EXIT_USAGE
    return EXIT_OK


def _cmd_rules(args: argparse.Namespace) -> int:
    if args.profile:
        try:
            profile = get_profile(args.profile)
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE
        rules = list(rules_for(profile))
    else:
        # Bind every rule to the first profile it applies to, purely so that a
        # citation can be rendered. The registry itself is profile agnostic.
        rules = []
        for spec in RULE_SPECS:
            target = next((p for p in PROFILES.values() if spec.applies(p)), None)
            if target is not None:
                rules.append(spec.bind(target))
    output = rules_to_json(rules) if args.format == "json" else rules_to_text(rules)
    sys.stdout.write(output)
    return EXIT_OK


def _cmd_profiles(_: argparse.Namespace) -> int:
    for pid, profile in sorted(PROFILES.items()):
        print(f"{pid}")
        print(f"  {profile.title}")
        print(f"  authority: {profile.authority}")
        print(f"  header   : {','.join(profile.header)}")
        print(f"  template : {profile.template_url}")
        print()
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "check": _cmd_check,
        "rules": _cmd_rules,
        "profiles": _cmd_profiles,
    }
    return handlers[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
