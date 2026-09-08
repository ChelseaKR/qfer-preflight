# Filer guide

A section per form, a worked example you can copy, and plain answers to the four
questions a report raises: what the exit code means, why a good file says
`UNVALIDATED`, when `--strict` is the right setting, and what an unevaluated
rule means for the decision to submit.

This guide explains the tool. It is not the filing instructions and does not
restate them. Each form's section links the Commission's published
instructions, which are the authority on who must file, when, and what a field
means. This is an independent utility and is not affiliated with, endorsed by
or approved by the California Energy Commission.

**Every example below is synthetic.** The rows were written for this guide.
The company numbers are made up and are not anyone's assigned number, the
amounts are invented, and no row is drawn from any real filing or describes
any real company's data. They exist so you can run the tool once and see what
its output looks like before you point it at a filing.

Terms in this guide, including advisory, unevaluated rule, UDC, LSE, TEOR and
UEG, are defined in `docs/glossary.md`.

## The one thing to understand first

**A well-formed file reports `UNVALIDATED`, not `PASS`.** That is the tool
working correctly, not a complaint about your data.

Four rules are published in Commission documents and cannot be tested
mechanically: QP005, QP018, QP032 and QP034. Rather than drop them, this
project registers them and reports them as unevaluated on every run, so their
absence can never be mistaken for their passing. Since at least three of them
apply to every form, no file ever reaches `pass`.

So the question a report answers is not "is this clean". It is "does anything
published say this is wrong, and what did nobody check". The second half is
printed every time, at length, with each rule's reason.

## Exit codes

| Code | Means | When |
|------|-------|------|
| `0` | No error-level findings | The tool read the file and no published rule was violated at error severity. Warnings, informational notes, advisories and unevaluated rules all still exit `0` without `--strict`. |
| `1` | At least one error-level finding | The verdict is `fail`. With `--strict`, also returned when anything was left unevaluated or an advisory was raised. |
| `2` | The tool was asked for something it could not do | An unknown profile, a file it cannot open, a header matching no published template with no `--profile` given, or a directory with no files in it. Nothing was validated. |

Two things are worth separating there. `1` is a statement about your file.
`2` is a statement about the invocation, and it means the run produced no
verdict at all rather than a bad one.

Checking several inputs at once aggregates them: `1` if any filing has
error-level findings, otherwise `2` if any input could not be processed,
otherwise `0`. An input that could not be processed is printed with its reason
and never dropped.

## When `--strict` is the right setting

Plain `check` exits `1` when published text says something in your file is
wrong. `--strict` widens that: it exits `1` when anything at all was left
unaccounted for, so an unevaluated rule or an advisory fails the run too.

Since at least three rules are permanently unevaluated on every form,
**`--strict` fails on every file, always.** That is not a bug and it is not useless. It is the setting for
a pipeline whose rule is "a human looks at anything the tool could not fully
account for", which for this tool is every submission.

Use it when:

- You want a build step that stops for review on every filing, including one
  whose only qualification is an advisory such as a byte order mark or a cell
  starting with `=`.
- You are checking whether a file raised any advisory at all, which the plain
  exit code will not tell you.

Do not use it when you want the exit code to mean "published rules were
violated". That is what plain `check` already means, and `--strict` mixes the
two claims together.

## What an unevaluated rule means for your filing decision

It means nobody checked, and that is all it means. It is not a pass and it is
not a failure.

Practically:

- **QP005**, totals rows. The instructions prohibit them and publish no way to
  tell a totals row from a data row. Check by eye that your export did not
  append a summary line.
- **QP018**, the "Valid NAICS codes" list. The list is not published anywhere
  this project can retrieve, and the Commission has said it does not plan to
  publish it. A code can be exactly six characters, pass QP017, and still be
  rejected on upload. If you have the data dictionary from your portal app
  landing page, that is where the list lives, and you can hand the list to this
  tool yourself: see "Checking NAICS codes against your own list" below.
- **QP032**, repeated reporting keys. No published document says which columns
  make a row unique, and the Commission's own worked example contains two rows
  that differ only in their amounts, so legitimate repeats exist.
- **QP034**, the workshop deck's instruction not to include commas anywhere in
  the file. Read literally it rejects every CSV the portal defines, since the
  comma is the delimiter. What is mechanical in the same sentence is checked
  by QP019, QP020 and QP033.

Each rule prints its own reason and its promotion condition in every report,
so you do not have to come back here to find out what would change.

## What an advisory means for your filing decision

An advisory is something the reader noticed, or had to do to your bytes, that
no published rule covers. It carries no severity and cites nothing, because
there is nothing to cite. It is not an assertion that the value is wrong.

It is still worth reading. `ADV-FORMULA-CELL` on a cell beginning `=` means a
spreadsheet may evaluate the cell rather than store it, so the value that
reaches a reviewer may not be the one you typed. `ADV-BOM` means the file
carries a byte order mark that the reader removed before matching the header.
Neither is published as an error by anyone. Both are things you would want to
know before uploading.

## How to read a finding

```text
[ERROR] QP020  cell J4 (row 4, Revenue): Revenue value "$15400.00" contains '$'.
```

- `QP020` is the rule. `qfer-preflight rules --profile <id>` prints its
  citation, its locator and the sentence it was transcribed from.
- `row 4` is the line number in the file, counting the header row as row 1.
  The first data row is row 2.
- `J4` is the same cell in spreadsheet terms: column J, row 4. Column letters
  follow the published template's column order.
- The message names the value it found and what the published text asks for
  instead.

Warnings and informational notes read the same way, with `[WARN]` and
`[INFO]`. Advisories read `[ADVIS]`, name a row and a column, and carry no
rule identifier.

## The five forms

Each section below gives the published header, a synthetic example you can
save and run, and exactly what the tool reports for it. The `Reported` line in
each section is held against a real run by
`tests/test_filer_guide.py`, so it cannot drift away from what the tool
actually does.

Run any of them the same way. `--profile` can be left out: the header is
matched against the five published templates, and detection proceeds only on
exactly one match.

```sh
uv run qfer-preflight check example.csv
```

### CEC-1306A-S1

CEC-1306A Schedule 1, UDC Electricity Sales and Deliveries Quarterly Report.
Authority: California Code of Regulations, Title 20, Section 1306(a).
Instructions:
<https://www.energy.ca.gov/sites/default/files/2025-07/1306A_Instructions_07142025_ada.pdf>

Synthetic example:

```csv
CompanyNumber,Year,Month,CountyNumber,CustomerType,RateClass,NAICSCode,NumberofCustomers,SalesDeliveryAmount,Revenue
1234,2025,7,19,B,Residential,RE1100,4820,15230000,2140500.75
1234,2025,8,19,B,Residential,RE1100,4831,14980000,2101300.10
1234,2025,9,37,D,Commercial,925190,12,86000,15400.00
```

Reported: status UNVALIDATED, 19 rules evaluated, 4 not evaluated (QP005,
QP018, QP032, QP034), 0 advisories, exit code 0.

Notes for this form:

- The seventh column is spelled `NumberofCustomers`, with a lower case "o".
  That is how the published template spells it and the header must match it
  byte for byte. See ADR 0002.
- `CustomerType` takes B, D or C. `O` is not an error here: it appears in the
  workshop deck and not in the instructions, so it produces QP025, an
  informational note. See ADR 0005.
- `NAICSCode` is checked for length by QP017 and for the published CEC custom
  codes by QP023. Membership of the "Valid NAICS codes" list is QP018 and is
  not checked.
- `RateClass` carries no published mechanical constraint. The instructions
  describe it as text. See `docs/column-coverage.md`.
- A data row that repeats the header row is an advisory on this form, not an
  error, because this form's instructions do not mention extra headers. See
  ADR 0007.

Why a rule says what it says, on this form:

```sh
uv run qfer-preflight explain QP024 --profile CEC-1306A-S1 --value 07
```

That prints the sentence the rule was transcribed from, the document and the
locator it sits at, the severity and why it is that severity, and, where a
value is given, what the engine itself says about that value. It invents
nothing: every line of it is already in the registry or is the check's own
message.

### CEC-1306A-S2

CEC-1306A Schedule 2, UDC Retail Rate Description Quarterly Report.
Authority: California Code of Regulations, Title 20, Section 1306(a).
Instructions:
<https://www.energy.ca.gov/sites/default/files/2025-07/1306A_Instructions_07142025_ada.pdf>

Synthetic example:

```csv
CompanyNumber,Year,QuarterNumber,RetailRatClass,Description
1234,2025,3,Residential,Synthetic example of a domestic rate class description
1234,2025,3,Commercial,Synthetic example of a small business rate class description
```

Reported: status UNVALIDATED, 10 rules evaluated, 3 not evaluated (QP005,
QP032, QP034), 0 advisories, exit code 0.

Notes for this form:

- The fourth column is spelled `RetailRatClass` in the published template.
  Reproduced deliberately; do not correct it. See ADR 0002.
- This is the only form with a `QuarterNumber` column, checked by QP012, and
  the only one with no month column, so QP011 and QP030 do not apply.
- No column on this form carries the shared numeric footnote, so QP019 and
  QP020 apply nowhere on it.
- `RetailRatClass` and `Description` carry no published mechanical
  constraint. Both were read for and closed as findings of nothing; see
  `docs/column-coverage.md`.
- QP018 is absent from the unevaluated list here only because this form has no
  NAICS column.

Why a rule says what it says, on this form:

```sh
uv run qfer-preflight explain QP012 --profile CEC-1306A-S2
```

That prints the sentence the rule was transcribed from, the document and the
locator it sits at, the severity and why it is that severity, and, where a
value is given, what the engine itself says about that value. It invents
nothing: every line of it is already in the registry or is the check's own
message.

### CEC-1306B

CEC-1306B, LSE Quarterly Report. Authority: California Code of Regulations,
Title 20, Section 1306(b). Instructions:
<https://www.energy.ca.gov/sites/default/files/2025-07/1306B_Instructions_07142025_ada.pdf>

Synthetic example:

```csv
CompanyNumber,Year,MonthNumber,UtilityDeliveryCompany,CustomerGroup,CountyNumber,NumberOfCustomers,SalesAmount,Revenue
5678,2025,7,PGE,Residential,1,3200,9100000,1450000.00
5678,2025,8,PGE,Commercial,1,410,7300000,1120000.50
5678,2025,9,SCE,Industrial,19,17,4200000,610000
```

Reported: status UNVALIDATED, 18 rules evaluated, 3 not evaluated (QP005,
QP032, QP034), 0 advisories, exit code 0.

Notes for this form:

- `UtilityDeliveryCompany` takes PGE, SCE or SDGE and nothing else, checked by
  QP022. The instructions ask for the value exactly as spelled with no special
  characters.
- `CustomerGroup` takes Residential, Commercial, Industrial or Other, compared
  case sensitively by QP015, because the instructions say the value must be
  entered exactly as spelled and capitalized.
- A data row that repeats the header row is a QP007 **error** on this form,
  because this form's instructions say to exclude extra headers. On
  `CEC-1306A` and `CEC-1308B` the same row is an advisory. See ADR 0007.

Why a rule says what it says, on this form:

```sh
uv run qfer-preflight explain QP022 --profile CEC-1306B
```

That prints the sentence the rule was transcribed from, the document and the
locator it sits at, the severity and why it is that severity, and, where a
value is given, what the engine itself says about that value. It invents
nothing: every line of it is already in the registry or is the check's own
message.

### CEC-1308B-S1

CEC-1308B Schedule 1, Gas Utility Deliveries and Revenue Quarterly Report.
Authority: California Code of Regulations, Title 20, Section 1308(c) and
1307(b). Instructions:
<https://www.energy.ca.gov/sites/default/files/2025-07/1308B_Instructions_07142025_ada.pdf>

Synthetic example:

```csv
CompanyNumber,Year,MonthNumber,CountyNumber,NAICSCode,RateCode,NumberOfCustomers,DeliveryVolume,Revenue
2468,2025,7,43,RE1100,10,15200,3100000,4150000.00
2468,2025,8,43,999999,30,88,940000,1210000.25
2468,2025,9,43,221311,50,6,120000,98000
```

Reported: status UNVALIDATED, 18 rules evaluated, 4 not evaluated (QP005,
QP018, QP032, QP034), 0 advisories, exit code 0.

Notes for this form:

- `RateCode` takes one of the eight published gas delivery codes, 10 through
  80 in steps of ten, checked by QP016.
- `NAICSCode` behaves as it does on `CEC-1306A-S1`: length by QP017, CEC
  custom codes by QP023, list membership unevaluated as QP018.
- A data row that repeats the header row is an advisory on this form, not an
  error. See ADR 0007.

Why a rule says what it says, on this form:

```sh
uv run qfer-preflight explain QP016 --profile CEC-1308B-S1
```

That prints the sentence the rule was transcribed from, the document and the
locator it sits at, the severity and why it is that severity, and, where a
value is given, what the engine itself says about that value. It invents
nothing: every line of it is already in the registry or is the check's own
message.

### CEC-1308C

CEC-1308C, Gas Retailer Quarterly Report. Authority: California Code of
Regulations, Title 20, Division 2, Section 1307(a). Instructions:
<https://www.energy.ca.gov/sites/default/files/2025-07/1308C_Instructions_07142025_ada.pdf>

Synthetic example:

```csv
CompanyNumber,Year,Month,CountyNumber,CustomerGroup,NumberOfCustomers,SalesDelivery,Revenue
1357,2025,7,15,Residential,9400,1250000,1875000.00
1357,2025,8,15,TEOR,4,830000,910000.50
1357,2025,9,15,UEG,2,1400000,1290000
```

Reported: status UNVALIDATED, 17 rules evaluated, 3 not evaluated (QP005,
QP032, QP034), 0 advisories, exit code 0.

Notes for this form:

- `CustomerGroup` takes a wider set than on `CEC-1306B`: Residential,
  Commercial, Industrial, TEOR, UEG or Other. The two abbreviations are
  defined in `docs/glossary.md`. QP015 compares them case sensitively.
- A data row that repeats the header row is a QP007 **error** on this form.
  See ADR 0007.

Why a rule says what it says, on this form:

```sh
uv run qfer-preflight explain QP015 --profile CEC-1308C
```

That prints the sentence the rule was transcribed from, the document and the
locator it sits at, the severity and why it is that severity, and, where a
value is given, what the engine itself says about that value. It invents
nothing: every line of it is already in the registry or is the check's own
message.

## A run that fails

The same `CEC-1306A-S1` shape, with six things wrong with it on purpose.
Synthetic, like everything else here.

```csv
CompanyNumber,Year,Month,CountyNumber,CustomerType,RateClass,NAICSCode,NumberofCustomers,SalesDeliveryAmount,Revenue
1234,2025,7,07,B,Residential,RE1100,4820,15230000,2140500.75
1234,2025,13,19,X,Residential,RE1100,4831,14980000,2101300.10
1234,2025,9,19,O,Residential,RE1100,NULL,86000,$15400.00
```

Reported: status FAIL, 19 rules evaluated, 4 not evaluated (QP005, QP018,
QP032, QP034), 0 advisories, exit code 1.

Six findings, at three severities. Each line below is the opening of a longer
message, quoted from the run rather than retyped, and the real output goes on
to say what to write instead:

```text
[ERROR] QP011  cell C3 (row 3, Month): Month value "13" is outside the published range.
[ERROR] QP014  cell E3 (row 3, CustomerType): CustomerType value "X" is not a published value.
[ERROR] QP019  cell H4 (row 4, NumberofCustomers): NumberofCustomers holds "NULL". Write a zero as 0.
[ERROR] QP020  cell J4 (row 4, Revenue): Revenue value "$15400.00" contains '$'.
[WARN]  QP024  cell D2 (row 2, CountyNumber): CountyNumber value "07" is the zero-padded form of '7', Contra Costa.
[INFO]  QP025  cell E4 (row 4, CustomerType): CustomerType value "O" is listed as valid by the DSP workshop deck (for BART, PGE only)
```

Four points about it:

- The four errors are the ones to fix. They exit `1`.
- **The `07` warning is more lenient than the portal.** The published sources
  do not agree about a zero padded County Number, so this tool reports a
  warning rather than an error, and it does not affect the exit code. The
  Commission has told this project directly that the portal rejects it. That
  answer is private correspondence, which a citation cannot rest on, so the
  severity stays where the published record puts it. Write the county number
  unpadded. ADR 0009 records the whole reasoning.
- The `O` note needs no action unless you file for BART.
- The report goes on to list the four unevaluated rules, as every report does.

## Checking a whole quarter at once

Point `check` at several files or a directory:

```sh
uv run qfer-preflight check ./q3-filings/
```

Each input keeps its own complete report and its own status line, findings
never merge across inputs, and a closing summary lists every input with its
status. An input the tool cannot process, such as a CSV whose header matches
no published template, appears in the summary as `NOT VALIDATED` with the
reason, rather than being skipped.

`--format json` produces a batch envelope, one embedded report per input,
conforming to `docs/schemas/report-batch-v1.schema.json`. `--format sarif` is
available for CI surfaces that read it.

## Checking NAICS codes against your own list

QP018 is unevaluated because this project has no copy of the Commission's
"Valid NAICS codes" list and will never ship one. You may have a copy. It is in
the data dictionary posted on the portal app landing pages, and Commission staff
will send it on request.

If you do, write the codes into a plain text file, one per line, and pass it:

```sh
uv run qfer-preflight check filing.csv --naics-list my-naics-codes.txt
```

The file is read from your disk and nowhere else. Nothing is uploaded, nothing
is cached, and no copy of your list is written into the report.

A list looks like this. These codes are synthetic:

```
221118
221122
RE1100
925190
```

Every line must be exactly six characters once its line ending is removed.
Nothing is trimmed or corrected, and a file that breaks the rule is refused
rather than partly read:

- a blank line, a header row, a comment, or a trailing space on any line;
- a byte order mark, which some editors add on save;
- anything that is not UTF-8 text;
- a file that is empty or cannot be opened.

A refused list does not stop the run. Every other rule still reports, and QP018
still reports as not evaluated, with the refusal as its reason and the same
sentence on standard error. That is deliberate: a code list read wrong is worse
than no code list, because one stray space turns a valid code into one that
matches nothing and the error would name a correct filing as wrong.

**What the report then says.** Findings under QP018 name your file's path and
its SHA-256, and the report's header block says the rule was evaluated against a
caller-supplied list rather than a published one. The `--format json` report
carries the same thing under `code_lists`. Your codes are never written into the
report: this tool does not republish a list it was handed, so hints count rather
than quote.

**What it does not mean.** A filing with no QP018 findings has matched the list
you supplied. This tool cannot check that your list is the Commission's, is
current, or is complete, and it does not claim to. `qfer-preflight rules` still
prints QP018 as not implemented, because the registry describes what this tool
ships and it ships no code list.

## Running it in CI

If your quarterly CSVs live in version control, the same run this guide has
been describing can happen on every push, or before every commit. Two surfaces
are published for that, and both carry the exit code contract above unchanged.

Nothing about your filing leaves the machine it runs on. The GitHub Action
downloads nothing and consults no package index: a composite action is checked
out at the reference you pin, the validator has no runtime dependencies, and
the action runs that checkout directly. The single exception is the optional
SARIF upload, which sends the report to your own repository's code scanning
alerts and nowhere else.

### A GitHub Action

```yaml
name: Validate the quarter

on:
  pull_request:
    paths: ["filings/**"]

permissions:
  contents: read

jobs:
  qfer:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: ChelseaKR/qfer-preflight@0000000000000000000000000000000000000000
        with:
          paths: filings/
```

Replace those forty zeroes with a real commit of this repository. Pinning is
covered below, and it is worth reading before you copy this.

| Input | Default | What it does |
|-------|---------|--------------|
| `paths` | required | What to validate, **one path per line**. Each line is a CSV file, or a directory whose files are validated in name order. One per line rather than a space separated list, so a path containing a space is not silently split into two paths that do not exist. |
| `profile` | detected | A form profile such as `CEC-1306A-S1`. Left empty, each file's header is matched against the published templates and only an exact match is accepted, so a folder holding five different forms needs no configuration. |
| `strict` | `"false"` | `"true"` adds `--strict`. Read the section above first: under strict, every form fails, because every form leaves rules unevaluated. |
| `format` | `"text"` | `text`, `json` or `sarif`. This is the report written to the log and to the report file. |
| `upload-sarif` | `"false"` | `"true"` sends the report to your repository's code scanning alerts. |

Two outputs are available to later steps: `exit-code`, the validator's own
code as a string, and `report-path`, the file the report was written to.

**The job status is the exit code.** Exit `0` is a green job. Exit `1`, error
level findings, and exit `2`, an invocation the tool could not carry out, are
both red. Nothing in the action can turn a non-zero code into a passing job.

That last point is the reason to run this in CI rather than trusting a green
check. Point the action at a directory with no files in it and the job fails,
because exit `2` means the run produced no verdict at all. A filing nothing
evaluated must never leave a green check behind. The same holds for a CSV
whose header matches no published template: the run refuses it rather than
guessing a profile, and the refusal reaches the job status.

### SARIF, and where the annotations land

```yaml
permissions:
  contents: read
  security-events: write

jobs:
  qfer:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: ChelseaKR/qfer-preflight@0000000000000000000000000000000000000000
        with:
          paths: filings/
          format: sarif
          upload-sarif: "true"
```

The upload happens whatever the verdict, because a filing with error level
findings is exactly the one whose annotations are worth having. The
unevaluated rules travel with it as SARIF notifications, so the annotation
view is not quieter than the report.

Asking for the upload without `format: sarif` is refused, and the job stops
before anything is validated. It is not skipped. A skipped upload would leave
an empty code scanning view beside a green job, and an empty view reads like a
clean filing.

One limitation to know before you turn this on. The report names each input by
its base name, and code scanning maps an alert to a file by its path relative
to the repository root. Alerts therefore land on the right lines only when the
filing sits at the root of the repository. From a subdirectory they still
arrive, and they still carry the rule, the message and the row, but they will
not attach to the file in the diff view.

### Pinning, and what the action can and cannot prove

Pin to a commit SHA. It is the strongest reference GitHub offers, and it is
the one form that cannot change under you.

A tag works too, from the first release that carries `action.yml`. It is not
in `v0.2.0`, which was published before this action existed, so check the
release notes rather than assuming any tag will do.

What the action cannot do is verify the signature on its own tag. Release tags
here are signed, and `.github/workflows/release.yml` verifies them at
publication time against the key committed at `.github/allowed_signers`. That
check needs a clone with full history and the tag objects in it. An action
checkout has neither, so there is nothing for the action to verify against and
it does not pretend otherwise. To check a signature yourself before pinning:

```sh
git clone https://github.com/ChelseaKR/qfer-preflight
cd qfer-preflight
git config gpg.ssh.allowedSignersFile .github/allowed_signers
git verify-tag v0.2.0
git rev-parse v0.2.0^{commit}
```

The last line prints the commit that tag names, which is what you pin.

The runner needs Python 3.12 or newer, which `ubuntu-latest` has. On an image
that does not, add `actions/setup-python` before the step. The action checks
the version and says so rather than failing later on an import.

### A pre-commit hook

```yaml
repos:
  - repo: https://github.com/ChelseaKR/qfer-preflight
    rev: v0.2.0
    hooks:
      - id: qfer-preflight
```

The `rev` has to be a revision carrying `.pre-commit-hooks.yaml`, which
`v0.2.0` does not. `pre-commit autoupdate` will move it to the newest tag,
which is the simplest way to get a current one.

The hook runs `qfer-preflight check` over the staged CSV files and nothing
else. It refuses a staged CSV whose header matches no published template,
because that is exit `2` and a run that could not identify the form validated
nothing. It refuses a filing with error level findings, because that is exit
`1`.

`--strict` is not on by default, and turning it on refuses every commit, since
every form leaves at least three rules unevaluated. If that is what you want,
say so explicitly:

```yaml
repos:
  - repo: https://github.com/ChelseaKR/qfer-preflight
    rev: v0.2.0
    hooks:
      - id: qfer-preflight
        args: [--strict]
```

The hook environment is built on the Python that runs `pre-commit`, and this
package requires 3.12 or newer. On an older interpreter the environment fails
to build, loudly, rather than the hook quietly not running.

## If you think a finding is wrong

Say so, with the document. A value this tool reports as an error that a
published Commission document calls valid is the most serious defect it can
have, because a validator that cries wolf is one people stop reading.

What to send is in `CONTRIBUTING.md`, under "Reporting a value the tool
rejects that a published document calls valid": the finding as printed, and
the published text that permits the value, with its URL and the locator inside
it. If the document differs from the one the rule cites, the outcome is not a
quiet patch. The error is withdrawn and the disagreement is reported instead,
citing both sources. QP024 and QP025 exist because that happened.

## What this tool will not tell you

- **Whether the portal will accept your file.** The Data Submission Portal is
  the authoritative validator. This tool reports what published documents say,
  and QP024 is a known case where the two differ.
- **Whether you must file, or which form.** Read the instructions linked in
  each section above.
- **Whether your numbers are right.** Nothing here checks a figure against
  anything except the published rules about how it must be written.
- **Anything about a column no published document constrains.** Those are
  mapped, cell by cell, in `docs/column-coverage.md`.

Your filing data never leaves your machine. The tool opens no network
connection, keeps no account, writes no telemetry and retains nothing.
