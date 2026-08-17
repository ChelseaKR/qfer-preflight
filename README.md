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
| QP030 | Months fall within one calendar quarter (warning) |
| QP031 | Rows share one reporting year (warning) |

Registered but **not implemented**, and reported as unevaluated on every run:

| Rule | Why it is not evaluated |
|------|--------------------------|
| QP005 | The instructions prohibit totals rows but publish no marker distinguishing a totals row from a data row. Any test would be a heuristic guess. |
| QP018 | The instructions require the NAICS code to match a list of "Valid NAICS codes", but that list is not published at any URL this project could retrieve. Length is still checked by QP017. |
| QP032 | No published document states which columns form a row's unique reporting key, so duplicates cannot be told from legitimate repeats. |

These three are the honest half of the tool. They are visible in every report
precisely so their absence is never mistaken for a clean result.

### What is deliberately out of scope

`CEC-1304` power plant generation reporting is not covered. It belongs to a
different QFER track, is filed by email or mail rather than through the CSV
portal, and its published form is a spreadsheet with no CSV template to
validate against. Rather than approximate it, this tool leaves it out.

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
