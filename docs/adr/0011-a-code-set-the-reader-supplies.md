# 0011. A code set the reader supplies

- Status: Accepted
- Date: 2026-09-08
- Extends: ADR 0009
- Relates to: ADR 0001

## Context

QP018 requires a NAICS Code to appear on the Commission's "Valid NAICS codes"
list. The list is published at no URL this project can retrieve, the search for
one is closed, and staff have written that there is no plan to publish it,
because it carries custom codes for particular utilities alongside CEC-defined
internal ones. ADR 0009 records that exchange and its consequence: the rule
stays registered, stays unevaluated, and reports itself on every run.

ADR 0009 also settled a harder question. Staff answered the county-number
question directly, and the answer was not used to sharpen QP024, because

> An error grounded in private correspondence is, from outside the project,
> indistinguishable from an invented one: both present a confident claim with
> nothing a reader can check behind it.

That is the rule this ADR has to be tested against, because a caller-supplied
NAICS list is also material a reader of the report may not hold.

The two situations are not the same, and the difference is who holds the
material. The correspondence is held by this project and by nobody else; a
report grounded in it asks its reader to take the project's word. A list passed
on the command line is held by the person running the tool, is named in the
report by path and digest, and is the reader's own document at the moment the
finding is produced. The route to it is one the Commission itself names: the
data dictionary on the portal app landing pages, or a request to staff.

The README has said for some time that a filer holding that document could
transcribe the list and implement the rule, and that doing so is a transcription
job rather than a research one. What was missing was a way to do it that did not
require forking this project.

## Decision

**`check --naics-list PATH` evaluates QP018 against a code list the caller
supplies. This project ships no list, fetches none, and the rule registry is
unchanged.**

Five conditions make that consistent with ADR 0009 rather than an exception to
it, and each is enforced rather than promised.

1. **The report says what it rested on.** The header block states that QP018 was
   evaluated against a caller-supplied list rather than a published one, and
   names the file's path as given, its SHA-256, its distinct code count and its
   line count. The JSON carries the same under `code_lists`. Every QP018 finding
   repeats the path and digest. A reader who did not run the tool is told, in
   the first thing they read, that this one rule is not like the others.

2. **The claim is never widened.** Nothing in the report says the list is the
   Commission's, is current, or is complete. It says where the codes came from.
   `qfer-preflight rules` still prints QP018 as not implemented, because the
   registry describes what this tool ships.

3. **The codes are never republished.** The Commission declined to publish that
   list. A report is a document a filer forwards, so the list does not travel in
   one: a hint names a transform of the filing's own value, which is already in
   the report, or counts how many codes share a prefix, and stops there.

4. **A refused list is not a missing list.** Reading fails closed on an
   unreadable file, a byte order mark, non-UTF-8 bytes, an empty file, or any
   line that is not exactly six characters once its line ending is stripped.
   Nothing is trimmed or corrected, because one trailing space turns a valid code
   into one that matches nothing and the resulting error would name a correct
   filing as wrong. A refusal leaves QP018 unevaluated **with the refusal as its
   reason**, distinct from the reason a run with no list carries. The status is
   `unvalidated` either way and `--strict` exits non-zero on both, exactly as ADR
   0001 requires.

5. **A run without the flag is unchanged.** The report is byte for byte what this
   tool has always written, in both renderings, and a test compares them as
   bytes. The `code_lists` key is absent rather than null.

The rule identifier does not move. QP018 means what it has always meant, cites
the same published sentence, and carries the same severity; what changed is that
a run can now be handed the material the citation refers to.

## Consequences

**The registry and a run can disagree about one rule, and that is the point.**
`spec.implemented` describes what this project ships. A run holding a caller's
list evaluates a rule the registry calls unimplemented, and every place that
filtered on `implemented` -- the ledger slots, the unimplemented registration,
the finding constructor's refusal, the header-block rule list -- now consults a
`grounded` set alongside it. The report's own contradiction check
(`_refuse_contradictions`) is what holds this together: a rule that ends in
neither `rules_evaluated` nor `rules_not_evaluated` is refused outright, so a
half-wired exception cannot ship quietly.

**A rule reached by this route is second-class on purpose.** It is not promoted,
not counted as implemented, and not usable as evidence about anybody else's
filing. Two filers running the same file against two different lists get two
different reports, and the digests in them are how a reader tells which is which.

**A precedent, and its limit.** This is a mechanism for one rule, and extending
it is a decision, not a configuration change. QP005, QP032 and QP034 are
unevaluated for reasons that no file a caller could hand in would settle: two of
them turn on what a published document does not say and one on a reading of a
sentence. Nothing here suggests those become flags. `--naics-list` exists because
a specific, enumerable code set exists, is held by the people who run this tool,
and is the only thing the rule was ever missing.

**What is still not permitted.** Bundling any list with this project, fetching
one, caching one, or writing one into a report. The Commission withheld that
document; this tool does not become the route around that.
