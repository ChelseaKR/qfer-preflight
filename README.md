# qfer-preflight

A deterministic, offline pre-submission validator for California Energy
Commission **QFER Consumption** CSV filings. You run it on your own data,
before you upload anything, and it tells you what a published rule says is
wrong with your file.

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

Show every rule with the text it was derived from:

```sh
uv run qfer-preflight rules --profile CEC-1306A-S1
```

Exit codes: `0` no error-level findings, `1` at least one error-level finding
(or, with `--strict`, anything left unevaluated), `2` bad invocation.

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
`CEC-1306A` Schedule 1 spells its seventh column `NumberofCustomers` with a
lower case "o", and Schedule 2 spells its fourth column `RetailRatClass`. The
job is to match what the portal expects, not what the template ought to say.

## Rules

Run `qfer-preflight rules` for the registry with full citations. Rule
identifiers are permanent: an identifier is never renumbered and never reused
for a different check.

Implemented and grounded in published text:

| Rule | Checks |
|------|--------|
| QP001 | Input is a non-empty file that parses as CSV |
| QP002 | Header matches the published template exactly, in order |
| QP003 | Every data row has the template's field count |
| QP004 | No blank rows |
| QP006 | At least one data row is present |
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
| QP025 | Customer Type is `O`, which two published documents disagree about (info) |
| QP030 | Months fall within one calendar quarter (warning) |
| QP031 | Rows share one reporting year (warning) |

Registered but **not implemented**, and reported as unevaluated on every run:

| Rule | Why it is not evaluated |
|------|--------------------------|
| QP005 | The instructions prohibit totals rows but publish no marker distinguishing a totals row from a data row. The workshop deck repeats the prohibition and illustrates it with a blank row, so it adds no marker either. Any test would be a heuristic guess. |
| QP018 | The instructions require the NAICS code to match a list of "Valid NAICS codes", but the reference resolves to nothing public. See below. Length is still checked by QP017. |
| QP032 | No published document states which columns form a row's unique reporting key, and the Commission's own worked example contains two rows that differ only in their reported amounts, so a legitimate repeat cannot be told from a duplicate. |

These three are the honest half of the tool. They are visible in every report
precisely so their absence is never mistaken for a clean result.

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
- The workshop deck says where the list actually lives: a "data dictionary
  showing expected data types and lists of valid values for fields that have
  common errors (e.g., NAICS code, county number, customer type, UDC name,
  etc.)", posted on the portal app landing pages, which require an account, or
  obtained by asking Commission staff.

It is also not safe to substitute the federal Census Bureau NAICS list. No CEC
text says the phrase means that, and the Commission's own accepted set demonstrably
includes codes Census does not publish, namely the `RE` series in the
residential table.

So QP018 stays registered and unevaluated. If you have the data dictionary from
your portal app landing page, the list can be transcribed and the rule
implemented; that is a transcription job, not a research one.

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

**Customer Type `O`.** The CEC-1306A instructions list D, B and C. Slide 9 of
the workshop deck lists "B (Bundled), D (Direct Access), C (Community Choice
Aggregator), O (for BART, PGE only)". `O` produces a QP025 informational note
naming both sources, not an error.

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

Published documents change. When they do, this tool is wrong until it is
updated. Check the rule citations against the current published instructions
before relying on a result.

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
