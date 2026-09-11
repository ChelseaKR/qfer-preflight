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
from collections.abc import Callable, Sequence
from pathlib import Path

from . import __version__
from .detect import read_header_bytes
from .diff import NotComparable, diff_reports, load_report, new_error_appeared
from .diff import to_json as diff_to_json
from .diff import to_text as diff_to_text
from .engine import TOOL_NAME, FindingRow, validate_path
from .explain import ExplainError, explain
from .explain import render_json as explain_json
from .explain import render_text as explain_text
from .findings_table import (
    TableHeader,
    render_findings_csv,
    render_findings_jsonl,
)
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
from .rules import all_rules, rules_for
from .supplied_codes import NaicsListOffer, offer_naics_list

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
        "--format",
        choices=("text", "json", "sarif", "findings-csv", "findings-jsonl"),
        default="text",
        help=(
            "output format. `findings-csv` and `findings-jsonl` write the ungrouped "
            "findings table -- one line per row and finding -- which is NOT the report "
            "and does not state which rules were never evaluated"
        ),
    )
    check.add_argument(
        "--findings-bom",
        action="store_true",
        help=(
            "prefix the findings table with a UTF-8 byte order mark. Off by default "
            "because it is not wanted anywhere else; Excel needs it to stop reading "
            "the file as the local code page"
        ),
    )
    check.add_argument(
        "--findings-dir",
        metavar="DIR",
        help=(
            "where to write one findings table per input, required when a findings "
            "format is used over more than one input. A batch writes a table per "
            "input and never one across inputs, because a table that concatenated "
            "two filings could not be sorted without mixing them"
        ),
    )
    check.add_argument(
        "--naics-list",
        metavar="PATH",
        help=(
            "a local file of NAICS codes, one per line, to evaluate QP018 against. "
            "The Commission does not publish its Valid NAICS codes list and this "
            "tool ships none; a filer who holds the portal's data dictionary can "
            "supply it here. The report records the file's path, SHA-256 and code "
            "count and says in words that the check rested on a caller-supplied "
            "list rather than a published one. Without the flag QP018 is reported "
            "as not evaluated, exactly as before"
        ),
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
        raw = read_header_bytes(path)
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


def _validate_one(
    path: str,
    profile: Profile | None,
    sink: Callable[[FindingRow], None] | None = None,
    naics: NaicsListOffer | None = None,
) -> BatchEntry:
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
        return BatchEntry(input_name=path, report=validate_path(path, chosen, sink, naics))
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


#: The two formats that write the ungrouped table rather than the report.
_FINDINGS_FORMATS = ("findings-csv", "findings-jsonl")


def _findings_output(
    entry: BatchEntry, rows: Sequence[FindingRow], fmt: str, *, byte_order_mark: bool
) -> str:
    """Render one input's findings table.

    `entry.report` is not optional here in practice -- a caller that could not
    produce a report takes the refusal path before this -- but the header still
    states every field as absent rather than guessing, because a table whose
    provenance is unknown is worth less than one that says so.
    """
    report = entry.report
    header = TableHeader(
        tool=TOOL_NAME,
        tool_version=__version__,
        profile_id=report.profile_id if report is not None else None,
        input_name=report.input_name if report is not None else entry.input_name,
        input_sha256=report.input_sha256 if report is not None else None,
        rows_read=report.rows_read if report is not None else None,
        status=str(report.status) if report is not None else "unvalidated",
        lines=len(rows),
    )
    if fmt == "findings-jsonl":
        return render_findings_jsonl(header, rows)
    return render_findings_csv(header, rows, byte_order_mark=byte_order_mark)


def _naics_offer(args: argparse.Namespace) -> NaicsListOffer | None:
    """Read `--naics-list` once for the whole run, and say on stderr if it was refused.

    The refusal also travels in every report, as QP018's not-evaluated reason,
    which is what a reader of the JSON sees. It is repeated here because stdout
    is the report and a person who mistyped a path is watching stderr. A refused
    list does not stop the run: the other twenty-odd rules are still worth
    reporting, and QP018 lands exactly where it lands with no list at all --
    unevaluated, dragging the status off `pass`, and non-zero under `--strict`.
    """
    path = getattr(args, "naics_list", None)
    if not path:
        return None
    offer = offer_naics_list(path)
    if offer.refusal is not None:
        print(offer.refusal, file=sys.stderr)
    return offer


def _check_single(path: str, args: argparse.Namespace) -> int:
    profile, problem = _resolve_profile(args)
    if problem is not None:
        print(problem, file=sys.stderr)
        return EXIT_USAGE
    collected: list[FindingRow] = []
    sink = collected.append if args.format in _FINDINGS_FORMATS else None
    entry = _validate_one(path, profile, sink, _naics_offer(args))
    if entry.report is None:
        # Reachable when --profile was omitted and detection refused the
        # header: single-file mode reports that refusal on stderr, exactly as
        # detection did before batch mode existed.
        print(entry.problem or "could not validate the input", file=sys.stderr)
        return EXIT_USAGE

    output = (
        _findings_output(entry, collected, args.format, byte_order_mark=args.findings_bom)
        if args.format in _FINDINGS_FORMATS
        else report_to_sarif(entry.report)
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

    if args.format in _FINDINGS_FORMATS:
        return _check_batch_findings(paths, profile, args)

    naics = _naics_offer(args)
    entries = [_validate_one(path, profile, None, naics) for path in paths]

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


def _check_batch_findings(
    paths: Sequence[str], profile: Profile | None, args: argparse.Namespace
) -> int:
    """One findings table per input, written as files. Never one table across inputs.

    A concatenated table cannot be sorted: sorting by row would interleave two
    filings whose row numbers mean different things. So a batch writes files, and
    refuses rather than guessing where to put them.

    The exit code is the batch contract unchanged. Writing tables is an output
    choice and must not make a failing run look like a passing one.
    """
    if args.findings_dir is None:
        print(
            f"--format {args.format} over {len(paths)} inputs needs --findings-dir: "
            "a batch writes one table per input, and concatenating them into one "
            "stream would produce a table nobody can sort.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    directory = Path(args.findings_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"could not use {directory} for findings tables: {exc}", file=sys.stderr)
        return EXIT_USAGE

    suffix = "csv" if args.format == "findings-csv" else "jsonl"
    naics = _naics_offer(args)
    entries: list[BatchEntry] = []
    for path in paths:
        collected: list[FindingRow] = []
        entry = _validate_one(path, profile, collected.append, naics)
        entries.append(entry)
        if entry.report is None:
            # No table for an input that produced no report. Writing an empty one
            # would be a file that reads as "nothing found here", which is the
            # opposite of what happened.
            print(f"{path}: {entry.problem or 'could not validate'}", file=sys.stderr)
            continue
        destination = directory / f"{Path(entry.input_name).stem}.findings.{suffix}"
        try:
            destination.write_text(
                _findings_output(entry, collected, args.format, byte_order_mark=args.findings_bom),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"could not write {destination}: {exc}", file=sys.stderr)
            return EXIT_USAGE
        print(f"{destination}: {len(collected)} line(s)")

    gaps = args.strict_ledger and [
        _report_ledger_gaps(entry.input_name, entry.report)
        for entry in entries
        if entry.report is not None
    ]
    statuses = [entry.report.status for entry in entries if entry.report is not None]
    if any(
        status is Status.FAIL or (args.strict and status is Status.UNVALIDATED)
        for status in statuses
    ):
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
        rules = list(all_rules())
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
