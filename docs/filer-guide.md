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
  landing page, that is where the list lives.
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
