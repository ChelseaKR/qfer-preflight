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
import sys
from collections.abc import Sequence

from . import __version__
from .engine import validate_path
from .model import Status
from .profiles import PROFILES, QFER_PROGRAM_URL, get_profile
from .report import rules_to_json, rules_to_text, to_json, to_text
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
    check.add_argument("path", help="path to the CSV file to validate")
    check.add_argument(
        "--profile",
        required=True,
        help="form profile, for example CEC-1306A-S1",
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


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        profile = get_profile(args.profile)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    try:
        report = validate_path(args.path, profile)
    except OSError as exc:
        print(f"could not read {args.path}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    output = to_json(report) if args.format == "json" else to_text(report)
    sys.stdout.write(output)

    if report.status is Status.FAIL:
        return EXIT_FINDINGS
    if args.strict and report.status is Status.UNVALIDATED:
        return EXIT_FINDINGS
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
