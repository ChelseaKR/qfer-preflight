# 0004. Disclose what the reader did, and what no published rule covers

- Status: Accepted
- Date: 2026-08-17

## Context

ADR 0001 closed the obvious false clean: a file that cannot be parsed, or a
header that does not match, leaves every dependent rule unevaluated and says
so. That contract was then tested against input designed to defeat it. Twenty
six hostile files were run through the tool. Several came back with **no
findings at all**.

The status line said `UNVALIDATED` in each case, because three rules are
permanently unimplemented, so no file ever reaches `pass`. But the body of the
report read `Findings: none`, the exit code was 0, and nothing in the output
distinguished the file from a well-formed one. `Findings: none` is what a
filer reads. Four distinct causes:

**The reader silently accepted a truncated file.** Python's `csv.reader`
reaches the end of the input inside an open quoted field, hands back whatever
it accumulated, and raises nothing. A file cut in half mid-value reported two
data rows and zero findings.

**Two published patterns matched values no portal would accept.** Python's
`\d` matches every Unicode decimal digit, and `int()` converts them. A Month
of `U+FF11` and a Year of `U+0662 U+0660 U+0662 U+0665` passed `QP011` and
`QP010` cleanly, as did a fullwidth amount under `QP020`.

**Cells no rule constrains were never mentioned.** A `CompanyNumber` of `=1+1`
and a `RateClass` of `@SUM(A1:A9)` produced an empty report, because no
published CEC text constrains those columns' contents. A spreadsheet opening
that file executes both.

**The reader repaired the bytes without saying so.** A UTF-8 byte order mark
was stripped before the header comparison, so a file whose header the portal
may well reject came back matching. Mixed and carriage-return line endings
were normalised the same way.

The first two are defects. The last two are the harder case: the tool noticed
something real, and had nothing to do with it, because reporting a finding
requires a citation and there is no published CEC text to cite. Under ADR
0001 the honest response to silence in the record is to say so loudly. Saying
nothing was the one option not available.

## Decision

**A report may not be quiet about something the reader noticed.** Three parts.

1. **Defects are fixed as defects.** An unterminated quoted field is a QP001
   error that blocks every other rule, on the same reasoning as any other
   unreadable input: the reader cannot know what the missing part would have
   said. Digit classes are written `[0-9]`, never `\d`. A parse failure part
   way through a file discards the findings gathered from the readable prefix,
   because that prefix was not validated either.

2. **Everything else the reader noticed becomes an advisory**, in a separate
   list with a separate code space, `ADV-...` rather than `QP...`. An advisory
   carries no severity and cites no CEC document. It says what is in the bytes,
   what the reader did about it, and that no published rule covers it. It is
   not a finding and must never be rendered as one.

3. **An advisory keeps the verdict away from `pass`.** `Report.status` returns
   `unvalidated` when any advisory is present, exactly as it does for an
   unevaluated rule, so `--strict` gates on both.

The advisories are `ADV-BOM`, `ADV-LINE-ENDINGS`, `ADV-FORMULA-CELL`,
`ADV-HIDDEN-CHARACTER` and `ADV-REPEATED-HEADER`. Each is capped at five
examples per column, with the total still reported, so a payload in every row
of a large file is a line with a count rather than a report nobody can read.

`ADV-FORMULA-CELL` deserves its own note, because it is the one that most
resembles a rule. A cell beginning `=`, `@`, tab or carriage return, or
beginning `+` or `-` and not being a plain number, is a cell a spreadsheet may
evaluate instead of storing. No CEC document says a word about it. The
advisory says as much in its own text. What it does not do is call the value
wrong, which would be exactly the invention ADR 0003 forbids.

## Consequences

Reports get longer, and a filer who has done nothing wrong may see an advisory
about a byte order mark their own tooling put there. That is the cost of the
rule, and it is the right way round: the alternative is a report that says
nothing about a file it silently repaired.

The advisory channel is a standing temptation to smuggle in checks that could
not survive as rules. The guard is structural rather than procedural: an
advisory cannot be reported at any severity, cannot appear in the findings
list, and cannot carry a citation, so an unfounded assertion has nowhere in
the output to go. `Advisory.__post_init__` rejects any code not beginning
`ADV-`.

The status change is the part with teeth. A report with an advisory and no
findings is `unvalidated`, so a caller running `--strict` in a gate now fails
on a byte order mark. That is intended. `--strict` means the tool has a
complete and unqualified account of the file, and an advisory is precisely a
qualification.

`tests/test_adversarial_input.py` holds the corpus. Its central assertion is
one line applied to every case: a report with no findings and no advisories
reads as a clean file, so no hostile input may produce one.
