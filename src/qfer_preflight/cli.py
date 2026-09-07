"""Command line interface.

Exit codes:
  0  no error-level findings
  1  at least one error-level finding, or, with --strict, anything the tool
     could not reach a verdict on: a rule that was not evaluated, or an
     advisory the reader raised, or, with --strict-ledger, a rule that judged
     no rows at all on a column this form carries
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
from .diff import NotComparable, diff_reports, load_report, new_error_appeared
from .diff import to_json as diff_to_json
from .diff import to_text as diff_to_text
from .engine import TOOL_NAME, validate_path
from .explain import ExplainError, explain
from .explain import render_json as explain_json
from .explain import render_text as explain_text
from .model import BatchEntry, Report, Status
from .profiles import PROFILES, QFER_PROGRAM_URL, Profile, detect_profiles, get_profile
from .report import (
    batch_to_json,
    batch_to_sarif,
    batch_to_text,
    report_to_sarif,
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
    check.add_argument(
        "--format", choices=("text", "json", "sarif"), default="text", help="output format"
    )
    check.add_argument(
        "--strict",
        action="store_true",
        help=(
            "also exit non-zero when any rule could not be evaluated or the "
            "reader raised an advisory"
        ),
    )
    check.add_argument(
        "--strict-ledger",
        action="store_true",
        help=(
            "also exit non-zero when a rule judged no rows at all on a column "
            "this form carries, whatever the reason. A clean filing can fail "
            "this: a rule with nothing to judge is still a rule that judged "
            "nothing"
        ),
    )

    rules = sub.add_parser("rules", help="list the rule registry with citations")
    rules.add_argument("--profile", help="limit to the rules that apply to one profile")
    rules.add_argument("--format", choices=("text", "json"), default="text", help="output format")

    explain_parser = sub.add_parser(
        "explain", help="print one rule's quote, locator and severity, and what a value does to it"
    )
    explain_parser.add_argument(
        "name", help="a rule identifier such as QP024, or an advisory code such as ADV-BOM"
    )
    explain_parser.add_argument(
        "--profile", help="read the rule as one form states it, rather than every form"
    )
    explain_parser.add_argument(
        "--value", help="run the engine's own cell checks over this value and print what it says"
    )
    explain_parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="output format"
    )

    sub.add_parser("profiles", help="list the supported form profiles")

    diff = sub.add_parser(
        "diff",
        help="compare two reports for the same filing and list what resolved, "
        "what is new and what is unchanged",
    )
    diff.add_argument("before", help="a single-report JSON document from the earlier run")
    diff.add_argument("after", help="a single-report JSON document from the later run")
    diff.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    return parser


_QUOTE = 0x22
_COMMA = 0x2C
_LINE_BREAKS = (0x0D, 0x0A)

# How much of the file to take at a time while looking for the end of the
# header. Large enough that a published header arrives in the first read, small
# enough that it is not a meaningful amount of memory.
_HEADER_CHUNK_BYTES = 1 << 16


class _HeaderScan:
    """Walks raw bytes looking for the end of the first CSV record.

    Only three bytes decide where a record ends: the quotation mark, which
    opens and closes a field a line break may sit inside, and the two line
    break characters themselves. All three are ASCII, and no ASCII byte ever
    appears inside a multi-byte UTF-8 sequence, so this can run on undecoded
    bytes without ever matching part of a character. That is the point: the
    bytes past the header must not be decoded at all.
    """

    __slots__ = ("_at_field_start", "_in_quotes", "_position")

    def __init__(self) -> None:
        self._at_field_start = True
        self._in_quotes = False
        self._position = 0

    def end_within(self, buffer: bytes | bytearray) -> int | None:
        """The index of the line break that ends the first record, if it is here.

        Resumable: the position and the quote state carry across calls, so the
        caller can keep handing over a longer buffer as it reads.
        """
        while self._position < len(buffer):
            byte = buffer[self._position]
            if self._in_quotes:
                if byte != _QUOTE:
                    self._position += 1
                elif self._position + 1 >= len(buffer):
                    return None  # a doubled quote and a closing one look alike here
                elif buffer[self._position + 1] == _QUOTE:
                    self._position += 2
                else:
                    self._in_quotes = False
                    self._at_field_start = False
                    self._position += 1
                continue
            if byte in _LINE_BREAKS:
                return self._position
            self._in_quotes = self._at_field_start and byte == _QUOTE
            self._at_field_start = byte == _COMMA
            self._position += 1
        return None


def _read_header_bytes(path: str) -> bytes:
    """The bytes of the file's first CSV record, and not one byte more.

    A file with no line break at all is one long record, so it is read whole,
    which is the same shape of cost the validation run already accepts: peak
    memory grows with the longest row, not with the size of the filing.
    """
    scan = _HeaderScan()
    buffer = bytearray()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(_HEADER_CHUNK_BYTES)
            if not block:
                return bytes(buffer)
            buffer.extend(block)
            end = scan.end_within(buffer)
            if end is not None:
                return bytes(buffer[:end])


def _detect_profile(path: str) -> tuple[Profile | None, str | None]:
    """Read the file's header row and match it against the published templates.

    Returns the one matching profile, or a refusal explaining why detection
    declined to guess. Detection reads the bytes of the first record and no
    more; it never validates, and a BOM stripped here is still reported by the
    validation run as ADV-BOM.

    Reading exactly those bytes is the contract, not an optimisation. Opening
    a text handle looks like it reads the header and does not: `TextIOWrapper`
    decodes a whole read-ahead block to satisfy one `next()`, so an invalid
    byte thousands of bytes past the header raised here and was reported as a
    fact about the first row, while the identical defect a little further into
    the file detected fine and got a report naming the offending byte. Which
    of the two a filing received depended only on where its bad byte fell
    relative to an 8 KB window that nothing documents. Decoding stops at the
    end of the record, so a `UnicodeDecodeError` caught below is now genuinely
    about the header, and everything past it is left to the reader, which
    names the byte exactly.
    """
    try:
        raw = _read_header_bytes(path)
    except OSError as exc:
        return None, f"could not read {path}: {exc}"
    try:
        header = next(csv.reader([raw.decode("utf-8-sig")]), None)
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


def _rules_that_judged_nothing(report: Report) -> list[str]:
    """Ledger entries where a rule judged no row of a column this form carries.

    The gate `--strict-ledger` reads. It looks only at entries naming a column,
    which is what excludes a rule the form publishes no column for: that rule
    judging nothing is a fact about the template, not about this filing.

    It does not sort the reasons into acceptable and unacceptable ones, and it
    is not meant to. A rule blocked by a wrong header and a rule with nothing
    in its published scope have judged the same number of rows, and a caller
    who has turned this on has said that number is what they are gating on.
    """
    return sorted(
        f"{entry.rule_id} on {entry.column}"
        for entry in report.evaluation
        if entry.column is not None and entry.judged == 0
    )


def _report_ledger_gaps(input_name: str, report: Report) -> bool:
    """Say on stderr which rules judged nothing, and whether any did.

    On stderr rather than stdout because stdout is the report, and a caller
    piping JSON into another tool must keep getting JSON. A non-zero exit with
    nothing said about why is the kind of gate people switch off.
    """
    silent = _rules_that_judged_nothing(report)
    if not silent:
        return False
    subject = "pair" if len(silent) == 1 else "pairs"
    print(
        f"{input_name}: {len(silent)} rule and column {subject} judged no rows: "
        f"{', '.join(silent)}. The evaluation ledger in the report says why each "
        "one judged nothing.",
        file=sys.stderr,
    )
    return True


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

    output = (
        report_to_sarif(entry.report)
        if args.format == "sarif"
        else to_json(entry.report)
        if args.format == "json"
        else to_text(entry.report)
    )
    sys.stdout.write(output)

    report = entry.report
    gaps = args.strict_ledger and _report_ledger_gaps(entry.input_name, report)
    if report.status is Status.FAIL:
        return EXIT_FINDINGS
    if args.strict and report.status is Status.UNVALIDATED:
        return EXIT_FINDINGS
    if gaps:
        return EXIT_FINDINGS
    return EXIT_OK


def _check_batch(paths: Sequence[str], args: argparse.Namespace) -> int:
    profile, problem = _resolve_profile(args)
    if problem is not None:
        print(problem, file=sys.stderr)
        return EXIT_USAGE

    entries = [_validate_one(path, profile) for path in paths]

    output = (
        batch_to_sarif(entries, TOOL_NAME, __version__)
        if args.format == "sarif"
        else batch_to_json(entries, TOOL_NAME, __version__)
        if args.format == "json"
        else batch_to_text(entries, TOOL_NAME)
    )
    sys.stdout.write(output)

    # Every entry is asked, not just the first one that answers yes, so a run
    # over a directory names every input with a silent rule rather than the
    # earliest.
    gaps = args.strict_ledger and [
        _report_ledger_gaps(entry.input_name, entry.report)
        for entry in entries
        if entry.report is not None
    ]

    statuses = [entry.report.status for entry in entries if entry.report is not None]
    had_findings = any(
        status is Status.FAIL or (args.strict and status is Status.UNVALIDATED)
        for status in statuses
    )
    if had_findings:
        return EXIT_FINDINGS
    if gaps and any(gaps):
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


def _cmd_explain(args: argparse.Namespace) -> int:
    """Re-render one rule out of the registry, and optionally run it over one value.

    Exit 2 on an unknown identifier. An explanation of a rule that does not exist would be an
    empty page, and an empty page reads as a rule with nothing to say about it.
    """
    try:
        payload = explain(args.name, profile_id=args.profile, value=args.value)
    except (ExplainError, KeyError) as exc:
        message = exc.args[0] if exc.args else str(exc)
        print(str(message), file=sys.stderr)
        return EXIT_USAGE
    sys.stdout.write(explain_json(payload) if args.format == "json" else explain_text(payload))
    return EXIT_OK


def _cmd_diff(args: argparse.Namespace) -> int:
    """Say what changed between two runs over one filing.

    Exit 1 only when an error-level finding is present now and was not before.
    A run whose findings all resolved exits 0 even though plenty changed:
    describing a change is not the same as objecting to one, and the filer is
    running this precisely because something changed.
    """
    try:
        before = load_report(Path(args.before))
        after = load_report(Path(args.after))
        diff = diff_reports(before, after)
    except NotComparable as exc:
        print(f"cannot compare these two reports: {exc}", file=sys.stderr)
        return EXIT_USAGE
    output = diff_to_json(diff) if args.format == "json" else diff_to_text(diff)
    sys.stdout.write(output)
    return EXIT_FINDINGS if new_error_appeared(diff) else EXIT_OK


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
        "explain": _cmd_explain,
        "diff": _cmd_diff,
    }
    return handlers[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
