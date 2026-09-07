# qfer-preflight

A deterministic, offline pre-submission validator for California Energy
Commission **QFER Consumption** CSV filings. QFER is Quarterly Fuel and
Energy Reporting; the expansion comes from the Commission's program page
title, and [`docs/glossary.md`](docs/glossary.md) records where it and every
other term here are published. You run it on your own data, before you
upload anything, and it tells you what a published rule says is wrong with
your file.

Every finding cites the published document it came from. Nothing else is
checked, and anything the tool cannot check is reported as **not evaluated**
rather than passed.

> This is an independent utility. It is **not affiliated with, endorsed by, or
> approved by the California Energy Commission**. It is not an official
> pre-screening service, and a clean run here is not an assurance that a
> filing will be accepted. The authoritative validator is the Commission's own
> submission portal.

## Quickstart

```sh
uv sync
uv run qfer-preflight profiles
uv run qfer-preflight check my-filing.csv --profile CEC-1306A-S1
```

`--profile` may be omitted. When it is, the tool reads the file's header row
and proceeds only on an exact match against one published template; zero
matches or several are a usage error, never a guess.

Several files, or directories, may be checked in one run. Each input keeps
its own complete report; findings never merge across inputs and nothing
aggregates them. The JSON output becomes a batch envelope,
`docs/schemas/report-batch-v1.schema.json`, embedding each single-report
document unchanged. An input that cannot be processed appears with its reason
stated, never dropped. Batch exit codes: `1` when any filing has error-level
findings, else `2` when any input could not be processed, else `0`.

Show every rule with the text it was derived from:

```sh
uv run qfer-preflight rules --profile CEC-1306A-S1
```

See what changed between two runs over the same filing, after you have edited
the spreadsheet and exported again:

```sh
uv run qfer-preflight check my-filing.csv --format json > before.json
# edit, re-export, re-run
uv run qfer-preflight check my-filing.csv --format json > after.json
uv run qfer-preflight diff before.json after.json
```

Every finding line is listed as resolved, new, changed or unchanged. A line is
identified by its rule, its column and its message text, which is the same
identity that decides whether two findings may be merged (ADR 0006), so a
problem you fixed in one row and reintroduced in another is reported as a
count and row change rather than as one problem vanishing and a different one
appearing. Advisories and unevaluated rules are compared the same way. It exits
`1` only when an error-level finding is present now and was not before, and `2`
when the two documents cannot be compared: different profiles, different schema
versions, or a batch envelope on either side. It suggests nothing about which
edit caused a change; it re-keys two reports and says which lines are the same
lines.

Exit codes: `0` no error-level findings, `1` at least one error-level finding
(or, with `--strict`, anything left unevaluated or any advisory raised, or,
with `--strict-ledger`, any rule that judged no rows on a column this form
carries), `2` bad invocation.

The JSON report conforms to a published schema,
`docs/schemas/report-v1.schema.json`, and carries its version as
`schema_version`. Additive fields are minor changes; removing or retyping a
field is breaking and moves the major version.

If you are filing rather than reading code, start with
[`docs/filer-guide.md`](docs/filer-guide.md): a section per form with a
synthetic worked example you can run, what each exit code means, when
`--strict` is the right setting, and what an unevaluated rule means for the
decision to submit. Its examples are held against real runs by
`tests/test_filer_guide.py`, so the guide cannot claim behaviour the tool does
not have. Terms the Commission's documents use, and the ones this tool's
reports use, are in [`docs/glossary.md`](docs/glossary.md).

## Using it from Python

A portal team, a filer's internal tooling or a notebook can validate without
shelling out. The supported names are the ones `qfer_preflight.__all__` lists;
everything else in the package is private and may move.

```python
from qfer_preflight import validate

report = validate("filing.csv")  # profile detected from the header
print(report.status)  # unvalidated
print(report.error_count)  # 0
print(len(report.rules_not_evaluated))  # 3
print(report.to_json())  # the same JSON `check --format json` prints
```

`validate` takes a path or bytes, and `profile=` when you would rather name the
form than have it detected. `report.to_json()`, `report.to_text()` and
`report.to_sarif()` produce exactly what the corresponding `check --format`
prints, byte for byte, because they call the same renderers. `profiles()` and
`rules(profile=None)` expose the registry.

Three guarantees come with these names:

- **Fail-closed travels with the API.** A filing that could not be read comes
  back as a `Report` whose verdict is not `pass`, never as an exception you
  have to interpret and never as a clean result.
- **Detection refuses rather than guessing.** A header matching no published
  template, or more than one, raises `ProfileDetectionError` naming the near
  misses. The near misses are advice for a person; nothing falls back to them.
- **Importing the package reads nothing.** No file is opened and no argument
  parser is imported at import time.

**Stability policy**, the same one the JSON report schema follows: adding a
name or an optional keyword argument is a minor version. Removing a name,
renaming one, or changing the type a name returns is a major version. Anything
not in `__all__` carries no promise at all.

## What it will not do

The tool runs entirely on your machine. It opens no network connection, has no
accounts, writes no telemetry, and never transmits the filing data you point it
at. Filing data is commercially sensitive and some of it is eligible for
confidential treatment, so it does not leave your machine.

## The one property that matters

**A document this tool could not evaluate never reports the same as a clean
one.**

That sounds obvious. It is the thing validators get wrong. If a file fails to
parse, or its header does not match the published template, a naive validator
runs zero row checks, finds zero problems, and prints "0 errors". The filer
reads that as "clean".

Here, that path is closed:

- An empty file, a file that is not valid UTF-8, or a file that is not CSV
  raises an error and leaves **every** other rule listed as unevaluated.
- A header that does not match the published template raises an error and
  leaves every column-dependent rule unevaluated, because without a correct
  header the engine cannot tell which column holds which field.
- A file with a valid header and no data rows is an error, not a pass.
- Rules that are published but not mechanically checkable are **permanently
  registered as unevaluated** and appear in every report.

Because of that last point, a spotless file reports `UNVALIDATED`, not `PASS`.
That is deliberate. The tool has no vocabulary for "clean" while any rule
remains unapplied. `tests/test_fail_closed.py` hashes the report for a clean
file, an empty file, and a malformed file, and asserts all three digests
differ.

### Advisories, and why they exist

`Findings: none` is what a filer reads, whatever the status line above it
says. So the promise above was attacked with twenty seven deliberately hostile
files, and four of them came back with an empty finding list: a file truncated
inside a quoted value, a Month written with a fullwidth digit, a cell
beginning `=`, and a file whose byte order mark the reader had quietly
stripped before matching the header.

The first two were defects and are fixed. The other two are the harder case:
the reader noticed something real and had nothing to say about it, because a
finding needs a citation and no published CEC text covers a leading `=` in a
`RateClass` or a byte order mark in a header. Those now produce **advisories**,
listed separately, with codes beginning `ADV-` rather than `QP`. An advisory
carries no severity, cites no CEC document, states in its own text that no
published rule covers it, and keeps the verdict away from `pass`. It is not a
rule and cannot be turned into one by accident: the model rejects any advisory
code that does not begin `ADV-`, and an advisory cannot be rendered as a
finding.

| Advisory | Raised when |
|----------|-------------|
| `ADV-BOM` | The file starts with a UTF-8 byte order mark, which the reader removed before reading anything else |
| `ADV-LINE-ENDINGS` | The file mixes line endings, or ends lines with a bare carriage return |
| `ADV-FORMULA-CELL` | A cell begins with a character a spreadsheet may evaluate as a formula |
| `ADV-HIDDEN-CHARACTER` | A cell holds an invisible character and no rule objected to the value |
| `ADV-REPEATED-HEADER` | A data row is an exact copy of the header row, on the three forms whose instructions do not mention extra headers. On the other two it is QP007, an error |

The code space is closed. An advisory cannot be constructed with a code that
is not in that table, and it cannot be constructed at all unless its own text
says the published record does not cover what it noticed, because that
sentence is the only place a reader learns there is no citation behind it.

ADR 0004 records the reasoning. `tests/test_adversarial_input.py` holds the
corpus, whose central assertion is one line applied to every case: a report
with no findings and no advisories reads as a clean file, so no hostile input
may produce one. `tests/test_advisory_channel.py` attacks the channel itself,
on the assumption that an output with no citation behind it is where an
invented check would try to enter.

### The evaluation ledger, and the rule that judged nothing

`Findings: none` is what a filer reads. The advisory channel above exists to
stop that line standing for something the reader noticed and could not cite.
The ledger exists to stop it standing for something no rule ever looked at.

`rules_evaluated` lists identifiers. It is true and it is not enough: a rule can
be listed there, correctly, having read every row in the file and reached a
verdict on none of them. So every report also carries an `evaluation` array,
one entry per rule and per column it touches, saying how many rows it was
offered, how many it judged, how many its own published applicability does not
reach, and how many an earlier rule left unreadable, with that rule named.

The numbers add up, and the type refuses an entry where they do not. A rule that
judged nothing carries a `zero_reason` of `no_applicable_rows`, `blocked_by` or
`column_absent`, and never carries one when it judged something, because a bare
`0` beside a rule identifier reads exactly like a clean result. `evaluated`
separates "ran and judged nothing" from "never ran".

It is a measurement of the run, not a check. It has no severity, cites nothing,
raises no finding and moves no verdict. `--strict-ledger` turns it into a gate
for callers who want one: exit non-zero when any rule judged no rows on a column
this form carries. A clean filing can fail that, and is meant to. On
`CEC-1308B-S1`, a file whose NAICS codes are all ordinary six-digit codes leaves
QP023, which reads the published residential classification table, with nothing
in its scope to judge. The ledger says so in as many words instead of reporting
a rule that ran and found no problems.

`docs/column-coverage.md` describes the entry shape and the two deliberate
asymmetries in it; `tests/test_evaluation_ledger.py` derives the ledger's rule
to column map from that document, so a rule the registry runs and the ledger
never counts fails the suite.

### Large files, and what a report will not do to fit

Filings run to hundreds of thousands of rows, and the mistakes that reach a
validator are usually systemic: one wrong county in a lookup table puts the
same finding on every row. Printing it 400,000 times is not a report.

The reader is also frugal with the file while it judges it. It walks the
bytes once, in chunks, keeping facts (a hash, line-ending counts, whether a
quoted field stayed open) rather than content, then streams rows to the
checker straight off disk. Peak memory grows with the longest row, not with
the size of the filing. `scripts/bench_large_file.py` measures that on a
synthesized filing if you want numbers.

Findings that are **identical** are merged into one line. Identical means the
same rule, the same column and the same message text, and since the message
contains the offending value, that means two rows wrong in the same way with
the same value. The line carries the count, the first five rows, and the last
one, so the merge loses nothing but the row numbers in between, which differ
from the ones shown in nothing except their position.

Nothing about that is left implicit. Each merged line says how many rows it
stands for, the heading says how many lines stand for how many findings, and a
closing line says how many were merged and on what terms. In JSON it is a
`collapsed` object carrying the policy and the count, and `counts` reports
`findings`, which counts rows, alongside `finding_lines`, which counts
entries. Severity counts are row counts: `error: 400000` means 400,000 bad
cells.

The one thing that is genuinely withheld is in the text rendering only. Where
one rule and column produce more than ten **distinct** findings, which happens
when every row is wrong in a different way and no merge is possible, the text
stops there, says how many it did not print, and points at `--format json`,
which contains every one. ADR 0006 records the whole design, including the
part of it that loses something.

## Supported profiles

| Profile | Form | Authority cited by the form |
|---------|------|------------------------------|
| `CEC-1306A-S1` | UDC Electricity Sales and Deliveries, Schedule 1 | Cal. Code Regs. tit. 20, s. 1306(a) |
| `CEC-1306A-S2` | UDC Retail Rate Description, Schedule 2 | Cal. Code Regs. tit. 20, s. 1306(a) |
| `CEC-1306B` | LSE Quarterly Report | Cal. Code Regs. tit. 20, s. 1306(b) |
| `CEC-1308B-S1` | Gas Utility Deliveries and Revenue, Schedule 1 | Cal. Code Regs. tit. 20, s. 1308(c) and 1307(b) |
| `CEC-1308C` | Gas Retailer Quarterly Report | Cal. Code Regs. tit. 20, div. 2, s. 1307(a) |

Headers are transcribed byte for byte from the published CSV templates,
including two irregularities that are reproduced rather than corrected:
`CEC-1306A` Schedule 1 spells its eighth column `NumberofCustomers` with a
lower case "o", and Schedule 2 spells its fourth column `RetailRatClass`. The
job is to match what the portal expects, not what the template ought to say.

## Rules

Run `qfer-preflight rules` for the registry with full citations. Rule
identifiers are permanent: an identifier is never renumbered and never reused
for a different check. The sequence has six holes in it, QP008, QP009 and
QP026 through QP029, and none of the six has ever been allocated to anything:
no rule was withdrawn and none was lost. Why the sequence was spaced that way
is not on the record, and ADR 0010 says so rather than supplying a reason it
cannot source. Every column of every published template is mapped to
the rules that touch it in `docs/column-coverage.md`, and a test holds that
map against the registry.

Implemented and grounded in published text:

| Rule | Checks |
|------|--------|
| QP001 | Input is a non-empty file that parses as CSV |
| QP002 | Header matches the published template exactly, in order |
| QP003 | Every data row has the template's field count |
| QP004 | No blank rows |
| QP006 | At least one data row is present |
| QP007 | The header row is not repeated among the data (`CEC-1306B` and `CEC-1308C` only, whose instructions say to exclude extra headers) |
| QP010 | Year is a four-digit calendar year |
| QP011 | Month is a whole number from 1 to 12 |
| QP012 | Quarter Number is 1 to 4 |
| QP013 | County Number is in the published county table |
| QP014 | Customer Type is D, B or C |
| QP015 | Customer Group matches a published value, capitalised exactly |
| QP016 | Rate Code is in the published gas rate code table |
| QP017 | NAICS Code is exactly six characters |
| QP019 | Numeric fields carry `0`, not blank, `NULL` or `-` |
| QP020 | Numeric fields carry no letters, spaces, separators or currency signs |
| QP021 | Company Number is present |
| QP022 | Utility Distribution Company is PGE, SCE or SDGE |
| QP023 | A residential `RE` code is in the published residential table |
| QP024 | County Number is zero padded, for example `07` (warning) |
| QP025 | Customer Type is `O`, published in the workshop deck and absent from the instructions (info) |
| QP033 | Company Number is written as digits alone, in the numeric or leading-zero text form the instructions publish |
| QP030 | Months fall within one calendar quarter (warning) |
| QP031 | Rows share one reporting year (warning) |

Registered but **not implemented**, and reported as unevaluated on every run:

| Rule | Why it is not evaluated |
|------|--------------------------|
| QP005 | The instructions prohibit totals rows but publish no marker distinguishing a totals row from a data row. The workshop deck repeats the prohibition and illustrates it with a blank row, so it adds no marker either. Any test would be a heuristic guess. |
| QP018 | The instructions require the NAICS code to match a list of "Valid NAICS codes", but the reference resolves to nothing public. The Commission has since said it does not plan to publish the list, so the search is closed and the promotion condition is declined rather than pending. See below. Length is still checked by QP017. |
| QP032 | No published document states which columns form a row's unique reporting key, and the Commission's own worked example contains two rows that differ only in their reported amounts, so a legitimate repeat cannot be told from a duplicate. |
| QP034 | The workshop deck says to "not include commas anywhere in the file". Taken literally that rejects every CSV the portal itself defines, since the comma is the delimiter; the narrower reading would be an interpretation, not a published test. Blank cells and non-numeric characters in the named fields are still checked by QP019, QP020 and QP033. |

These four are the honest half of the tool. They are visible in every report
precisely so their absence is never mistaken for a clean result. Each one's
reason text also states its own promotion condition: the published evidence,
and only that evidence, which would turn it into an implemented rule.

### The missing "Valid NAICS codes" list

QP018 is the one worth explaining, because the list it needs plainly exists
somewhere. Here is where it was looked for and what turned up.

- The QFER program page links nine documents: four instruction PDFs and five
  CSV templates. None is a NAICS list, and no archived snapshot of that page
  has ever linked one.
- The phrase is not a hyperlink in either instruction PDF, and neither PDF
  carries a NAICS appendix. The only six-digit codes printed anywhere in them
  are the four CEC custom codes (`925190`, `221311`, `221312`, `999999`).
- The sitemap was walked, and the `/media/` identifier space around the QFER
  documents was enumerated directly, because the sitemap does not cover all of
  it. No item's title or filename contains "NAICS".
- Guessed filenames under `/sites/default/files/` all returned 404.
- The portal at `datasubmission.energy.ca.gov` validates uploads in the browser
  with a generic JSON Schema engine whose schemas, and therefore whose lists of
  valid values, are served only after sign-in. The public asset carries no code
  list of its own.
- `ecdms.energy.ca.gov`, the Commission's older Energy Consumption Data
  Management System, does not resolve. That is not a transient fault: the host
  returns NXDOMAIN from every resolver tried, because the system is retired.
  Its successor is the Energy Consumption Data Files page, which was retrieved
  and read on 2026-08-17. It publishes no NAICS code list, no customer type
  list and no rate class list. The `SECTOR` column in its files holds
  descriptive text such as "Agriculture and Water Pumping" rather than a code,
  and no six digit value appears anywhere in either file read.
- The workshop deck says where the list actually lives: a "data dictionary
  showing expected data types and lists of valid values for fields that have
  common errors (e.g., NAICS code, county number, customer type, UDC name,
  etc.)", posted on the portal app landing pages, which require an account, or
  obtained by asking Commission staff.
- So the Commission was asked. Staff answered on 2026-08-26 that the list is
  not posted on a public website and that there is no plan to post it, because
  it carries custom NAICS codes for certain utilities alongside CEC-defined
  codes for internal use, and that the data dictionary holding it is an
  internal deliverable they are not permitted to share publicly. For the
  standard codes in the set that are neither custom nor CEC-defined, they
  point to <https://www.census.gov/naics/>, which defines codes already known
  to be in the set rather than supplying the set.

It is also not safe to substitute the federal Census Bureau NAICS list. No CEC
text says the phrase means that, and the Commission's own accepted set demonstrably
includes codes Census does not publish, namely the `RE` series in the
residential table.

So QP018 stays registered and unevaluated, and the search for a published copy
is closed rather than merely unfinished. The routes the Commission itself names
are the portal app landing pages, which require an account, and a request to
Commission staff. Neither produces a document published at a URL this project
can cite, and the Commission has now said it does not intend to change that.
The rule's promotion condition is therefore declined at the source rather than
pending, which is a different state for a reader to see and is what its reason
text now reports. ADR 0009 records the exchange. If you have the data
dictionary from your portal app landing page, the list can be transcribed and
the rule implemented; that is a transcription job, not a research one.

### Where the published documents disagree with each other

Two Commission documents contradict each other in two places. In both, the
tool declines to report an error and reports the disagreement instead, because
a validator that flags a value the Commission itself documents as valid is one
that filers learn to ignore. ADR 0003 records the reasoning.

**Zero-padded County Number, for example `07`.** The published county table
writes counties 1 to 58 unpadded and writes only Unknown as `00`. But
formatting rule 6 in the DSP workshop deck reads: "Any Company Number, County
Number, and NAICS code values that contain a leading 0 (zero) should be
formatted as TEXT data type." That tells a filer how to keep a leading zero on
a County Number rather than calling the value wrong, and no published source
calls the padded form an error. The Commission's own published error example
for the field is a negative number, `-24`, while its published warning example
is a plausible but suspect value, `14 instead of 41`. So `01` through `09` are
a QP024 warning, not a QP013 failure. `00` is in the table and is silent.
`007` has no published cover at all and remains an error.

A second CEC dataset, the county level table on the Energy Consumption Data
Files page, was read on 2026-08-17 and corroborates the county code set
independently: 58 distinct county numbers, 1 through 58, every one unpadded,
with a number to name mapping agreeing with the instruction table on 57 of the
58. That is a second Commission publication, from a different programme,
arriving at the same codes, so the transcribed table is not a misreading of one
document. It does not turn padding into an error, for three reasons recorded in
ADR 0008: no published source says a filer must not pad, the county numbers in
that file are stored as spreadsheet numbers and so cannot carry a leading zero
whatever was intended, and the dataset is aggregate consumption reporting
rather than a QFER filing, so it says nothing about what the portal accepts.
The warning stands, on better evidence than it had.

The Commission has since answered the question outright. Asked whether the
portal accepts `07`, staff replied on 2026-08-26 that only integer values of
1 to 58 and `00` are accepted, and that a single digit county number carrying a
leading zero will generate an error. **QP024 is still not an error.** That
reply is authoritative and it is private correspondence: a filer cannot open
it, and neither can anyone else weighing whether to trust a finding. An error
resting on a source the reader cannot check is, from outside, indistinguishable
from an invented one, and holding that distinction is the whole of what this
tool is for. So the severity stays where the published record puts it. What
changed is that the warning is now known to be more lenient than the portal
rather than merely unconfirmed, and that is said here instead of left to be
inferred. Write the county number unpadded, which is what the warning already
tells you to do. ADR 0009 records the exchange and the reasoning.

**Customer Type `O`.** The CEC-1306A instructions list D, B and C. Slide 9 of
the workshop deck lists "B (Bundled), D (Direct Access), C (Community Choice
Aggregator), O (for BART, PGE only)". `O` produces a QP025 informational note
naming both sources, not an error.

That call was re-examined, because the obvious objection is that the
instructions were revised three weeks *after* the deck, which would make the
deck a superseded draft. The published record does not support that reading.
The July 2025 instructions carry no change log, errata or revision history,
and neither do the three sibling documents reissued the same day. More to the
point, `O` was never in the instructions to withdraw: the previous published
revision, which the Commission's forms page still linked in May 2025 and which
remains live, reads "4. Customer Type. D = Direct Access Customer. B = Bundled
Customer." Two values. The pre-portal Excel form carries the same pair. So the
sequence runs B and D, then B, D and C, and the July revision's net change was
to **add** C. No revision has ever removed `O`, and nothing published since
mentions it either way. ADR 0005 records the search and its outcome. The call
flips only on published text stating that `O` is not accepted. The data
dictionary slide 44 promises would have been that text, and the Commission has
since said it will not be published, so that route is closed. Asked directly,
staff confirmed on 2026-08-26 that `O` is accepted, that only Pacific Gas and
Electric report it, and that another agency reporting it draws a portal warning
rather than a rejection. That is the posture QP025 already takes, reached from
the published record alone. The note is unchanged in substance, because a rule
that cites the deck goes on citing only the deck. ADR 0009 records it.

### Where the forms ask for different things

Separately from the two disagreements above, the five instruction documents do
not all say the same thing, and where they differ the rules differ with them.

The "Important Template Notes" sentence is the clearest case. `CEC-1306B` and
`CEC-1308C` read "Exclude any extra information, including extra headers, data
for other fields, miscellaneous calculations, blank rows, or totals."
`CEC-1306A` and `CEC-1308B` publish the same sentence without the words "extra
headers". So a data row that is an exact copy of the header row is a QP007
error on the first two forms and an `ADV-REPEATED-HEADER` advisory on the
other three. The observation is the same either way; what differs is whether
there is anything to cite. ADR 0007 records it.

### What is deliberately out of scope

`CEC-1304` power plant generation reporting is not covered. It belongs to a
different QFER track, is filed by email or mail rather than through the CSV
portal, and its published form is a spreadsheet with no CSV template to
validate against. Rather than approximate it, this tool leaves it out.

`CEC-1306A` Schedule 3 and `CEC-1308B` Schedule 2 are not covered either. Both
are submitted by SFTP rather than through the portal, and the workshop deck
directs their filers to email the Commission for the instructions and the
template. Neither template is published, so there is nothing to transcribe.

## Sources

Every rule traces to one of these. They were read directly, not summarised
from secondary sources.

- QFER program page:
  <https://www.energy.ca.gov/rules-and-regulations/energy-suppliers-reporting/quarterly-fuel-and-energy-reporting-qfer>
- CEC-1306A instructions (rev. 07/14/2025):
  <https://www.energy.ca.gov/sites/default/files/2025-07/1306A_Instructions_07142025_ada.pdf>
- The previous published revision of the CEC-1306A instructions, still live and
  still linked by the Commission's forms page in May 2025. It is read for one
  purpose only, in ADR 0005: to establish what the Customer Type list said
  before the current revision. No rule cites it.
  <https://www.energy.ca.gov/sites/default/files/2020-08/1306A_Instructions_ada.pdf>
- CEC-1306B instructions (rev. 07/14/2025):
  <https://www.energy.ca.gov/sites/default/files/2025-07/1306B_Instructions_07142025_ada.pdf>
- CEC-1308B instructions (rev. 07/14/2025):
  <https://www.energy.ca.gov/sites/default/files/2025-07/1308B_Instructions_07142025_ada.pdf>
- CEC-1308C instructions (rev. 07/14/2025):
  <https://www.energy.ca.gov/sites/default/files/2025-07/1308C_Instructions_07142025_ada.pdf>
- Published CSV templates, which supply the exact header rows:
  `1306A_S1_template.csv`, `1306A_S2_template.csv`, `1306B_template.csv`,
  `1308B_S1_template.csv`, `1308C_template.csv`, all under
  <https://www.energy.ca.gov/sites/default/files/2025-07/>
- QFER Consumption Data Submission Portal (DSP) Workshop slides, June 24, 2025:
  <https://www.energy.ca.gov/sites/default/files/2025-06/QFER_DSP_Workshop_ada.pdf>
  This deck states submission rules the instruction PDFs do not, and it is the
  source for QP024 and QP025. It is a slide deck, and it predates the current
  instructions by three weeks, so it is used only to withhold an error, never
  to add one.
- Energy Consumption Data Files, the CEC page that succeeded the retired
  `ecdms.energy.ca.gov`:
  <https://www.energy.ca.gov/files/energy-consumption-data-files>
  Two files from it were retrieved and read on 2026-08-17. Neither is a QFER
  filing document and no rule cites either. They are listed because a source
  that was checked and found not to contain something is worth the same as one
  that did, and because the first corroborates the county table.
  - `AGG_CONSUMPTION_ELEC_COUNTY_TBL_ada.xlsx`,
    <https://www.energy.ca.gov/filebrowser/download/8144>. Columns `YEAR`,
    `COUNTY_NUM`, `COUNTY_NAME`, `SECTOR`, `RNR`, `GWH`, over 14,168 data rows
    for 1990 to 2024. **Contains** 58 distinct county numbers, 1 through 58,
    all unpadded, agreeing with the instruction table's names on 57 of the 58.
    **Does not contain** any zero padded county number, any `00` or `99`, any
    NAICS code, any customer type or any rate class. Its `SECTOR` column is
    descriptive text. See ADR 0008, which also records the two defective rows
    in it.
  - `AGG_CONSUMPTION_ELEC_UTILITY_TBL_ada.xlsx`,
    <https://www.energy.ca.gov/filebrowser/download/8168>. Columns `YEAR`,
    `PLANNING_AREA`, `AGENCY_NAME`, `AGENCY_TYPE`, `SECTOR`, `RNR`, `GWH`.
    **Contains** utility names and planning areas. **Does not contain** any
    NAICS code, customer type or rate class; its `SECTOR` is descriptive text
    such as "Agriculture and Water Pumping", and no six digit value appears in
    it anywhere. It grounds no rule and closes part of the QP018 search.

One source in this list is not a document and cannot be cited by anything:

- Correspondence with the Commission's Consumption Data Analytics Unit,
  2026-08-17 to 2026-08-26, in reply to questions from this project about
  where the "Valid NAICS codes" list is published, whether the portal accepts
  a zero padded County Number, and whether Customer Type `O` is still
  accepted. All three were answered. **No rule cites it and no rule ever
  will**, because a citation here has to name something a reader can open, and
  private email is not that. It is listed for the same reason the sources that
  grounded nothing are listed: so a later reader knows the ground was covered.
  What it settles, and what it deliberately does not move, is recorded in
  ADR 0009.

Published documents change. When they do, this tool is wrong until it is
updated. Check the rule citations against the current published instructions
before relying on a result. `docs/source-manifest.md` records the SHA-256 and
retrieval date of every document cited here, so a revision can be detected by
comparing hashes rather than by rereading everything.

## Development

```sh
make verify
```

That runs formatting, linting, typing, security scanning and the tests with
the coverage floor, and is the same set CI runs.

## Standards Conformance

Every standard below is `Applies`, `Applies (gap tracked in #NN)`, or
`N/A: <reason>`. No blank cells.

| Standard | State |
|----------|-------|
| Responsible-Tech Framework | Applies |
| Code Quality | Applies |
| Security & Supply-Chain | Applies |
| CI/CD | Applies |
| Release & Versioning | Applies |
| Observability | Applies: lowest tier. An offline single-run CLI emits no telemetry by design; the run report is the only output. |
| Performance | N/A: no hosted route and no browser bundle, so there is no latency or bundle budget to hold. Work is bounded by local CSV size. |
| Accessibility | N/A: no HTML or UI surface. Output is plain text or JSON on stdout. |
| Internationalization | N/A: English-only, matching the source documents. See `docs/I18N.md`. |
| AI Evaluation | N/A: no model, prompt, or retrieval surface. The engine is deterministic. |
| Documentation | Applies |
| Quality & Metrics | Applies |
| AI Development Measurement | Applies |
| Incident Response | Applies |
| Data Governance | Applies: reads filing data locally, retains nothing, transmits nothing. |

## License

Apache-2.0. See `LICENSE`.
