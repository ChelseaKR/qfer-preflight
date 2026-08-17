# 0006. Merge identical findings, and say what was merged

- Status: Accepted
- Date: 2026-08-17

## Context

A quarterly UDC filing is large. Hundreds of thousands of rows is ordinary,
and the mistakes that reach a validator are usually systemic rather than
scattered: a county lookup that maps to the wrong number, an export that
writes `NULL` into every empty amount, a NAICS column carrying five-digit
codes throughout. One wrong mapping puts the same finding on every row.

The tool reported each of them. A 400,000 row file with a bad county in every
row produced 400,000 findings, all carrying the same three hundred character
message, differing only in the row number. Three things were wrong with that.

**It is unreadable.** The filer needs one fact, that the county column is
wrong everywhere, and has to scroll past 400,000 lines to be sure that is what
they are looking at rather than 400,000 different problems.

**It buries the rest of the report.** A single systemic error hides the four
unrelated ones underneath it, which are the findings the filer would not have
found on their own.

**It is expensive.** One `Finding` object per bad cell, each holding its own
copy of the same message, before anything gets the chance to summarise them.

Advisories already had an answer: at most five examples per column, with the
total still reported. Findings did not, and the reason they did not is worth
recording, because it is a good reason. An advisory says something no rule
covers. A finding is a cited assertion that a specific value in a specific
cell violates published text, and a cap on those is a validator hiding real
errors, which is the exact defect this project exists to avoid. A previous
pass looked at this and left it alone rather than truncate.

## Decision

**Findings that are identical are reported once, with everything that made
them identical.** Two findings are the same finding when their rule, their
column and their message text all match. Nothing else merges.

That distinction is what makes this a merge rather than a cap. The message
already contains the offending value, so two rows only produce one line when
they are wrong in the same way with the same value, and the single line is a
complete account of both. A merged finding carries:

- `occurrences`, how many rows produced it;
- `row` and `cell`, the first of them, unchanged from before;
- `example_rows`, the first five;
- `last_row`, the far end of the run.

So the systemic case reads as one line saying that 400,000 rows carry it, from
row 2 to row 400,001, starting with rows 2, 3, 4, 5 and 6. Nothing a filer
would act on is gone: the fix for row 250,000 is the fix for row 2.

**The report states the merge.** Every line that stands for more than one row
says so underneath itself, the heading says how many lines stand for how many
findings, and a closing line says how many were merged and on what terms. The
JSON rendering carries the same in a `collapsed` object with the policy
written out, and `counts` reports both `findings`, which counts rows, and
`finding_lines`, which counts the entries. A caller reading either format
learns what happened without having been told to look for it.

**Severity counts count rows.** `error` in the counts block is the number of
occurrences, not the number of lines, because a filer asking how many errors
they have is asking about their data and not about the report's layout.

**The text rendering, and only the text rendering, stops after ten distinct
findings for one rule and column.** This is the one place something is
genuinely withheld, and it is the case merging cannot reach: 400,000 rows each
wrong in a different way produce 400,000 different messages, and no honest
merge combines them. The text says exactly how many it did not print and for
which rule and column, and points at `--format json`, which contains every
one. A machine-readable rendering that holds everything is what makes it
acceptable to bound the human one.

## Consequences

The merge is not free of loss, and the loss should be named: the row numbers
between the fifth example and the last go unreported in both formats. That is
the deliberate trade, and it is bounded by the merge key. Those rows differ
from the reported ones in nothing except their position, because a difference
in anything else would have produced a different message and therefore a
different line.

`Finding` grew four fields, and every consumer of `error_count` now gets a row
count rather than a line count. Both are breaking changes to the JSON
contract, recorded in the changelog.

The text limit is the part to watch. It is disclosed, per rule and per column,
and it never applies to the JSON, but it is still a report withholding
something, which is the thing this project is most careful about. If it turns
out to bite on real filings, the answer is a flag that lifts it, not a quieter
limit.

## Also decided here: a parse failure keeps what was observed about the file

ADR 0004 established that a CSV parse failure part way through a file discards
the findings gathered from the readable prefix, because that prefix was not
validated either. That holds and is not reopened.

It went too far in one respect. The advisories went with the findings, and two
of them are not about the file's contents at all. `ADV-BOM` says there is a
byte order mark on the front of the file. `ADV-LINE-ENDINGS` says the file
does not settle on one line terminator. Both are true of the bytes whether or
not the reader reached the end of them, and a stray carriage return is a
plausible reason the reader did not, so the report most likely to have been
caused by one of them was the report that said least about it.

File-level advisories now survive a parse failure. Row-level ones do not, on
the same reasoning as the findings: they came from rows that were never
validated. `ADV-BOM` is also raised before the file is decoded rather than
after, so a file that is not UTF-8 still reports the mark on its front, and
its wording no longer claims anything about a header check that may never have
happened.
