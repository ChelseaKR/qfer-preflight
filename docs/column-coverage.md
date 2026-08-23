# Column coverage

This map answers one question per column of every published template: which
registered rules touch it. It exists so that the space between checks is
visible instead of silent, and so that "nobody wrote a rule for this column"
looks different from "nothing published constrains it".

It is kept honest by `tests/test_column_coverage.py`, which asserts three
things: every column of every profile header appears here, in order; every
rule identifier named here exists in the registry; and every identifier in the
registry is named here. A new column or a new rule cannot skip the map without
failing the suite.

## How to read the tables

- A rule identifier means a rule whose applicability names that column.
- `QP019` and `QP020` together are written "numeric hygiene": they apply to
  every column the instructions mark with the shared numeric footnote.
- "none registered yet" means no rule names the column today. Those columns
  sit on the Phase 3 reading list in `ROADMAP.md`, which records what has to
  happen before one appears: a quote, then a decision. It is not a claim that
  the instructions publish nothing about them.
- `(unevaluated)` marks a registered rule that evaluates to nothing by
  design, with its reason stated in the registry and repeated in every report.

## Checks that hold the file together

These apply to the submission as an object rather than to any one column:

| Rule | Holds | State |
|------|-------|-------|
| QP001 | Parses as CSV, non-empty | evaluated |
| QP002 | Header matches the published template byte for byte | evaluated |
| QP003 | Every data row has the template's field count | evaluated |
| QP004 | No blank rows | evaluated |
| QP005 | No totals or summary rows | unevaluated |
| QP006 | At least one data row | evaluated |
| QP007 | Header row not repeated among the data | evaluated, CEC-1306B and CEC-1308C only |
| QP032 | No repeated reporting key | unevaluated |

Where QP007 does not apply, the same observation stays available as the
`ADV-REPEATED-HEADER` advisory. Advisories are not rules and carry no
citation; see `docs/adr/0004-disclose-what-the-reader-did-and-what-no-rule-covers.md`.

Cross-row checks attach to columns rather than to the whole file: `QP030`
follows the Month column and `QP031` follows the Year column wherever those
columns exist.

## CEC-1306A-S1

UDC Electricity Sales and Deliveries, Schedule 1.

| Column | Rules |
|--------|-------|
| CompanyNumber | QP021 |
| Year | QP010, cross-row QP031 |
| Month | QP011, cross-row QP030 |
| CountyNumber | QP013, QP024 |
| CustomerType | QP014, QP025 |
| RateClass | none registered yet |
| NAICSCode | QP017, QP023, QP018 (unevaluated) |
| NumberofCustomers | numeric hygiene QP019, QP020 |
| SalesDeliveryAmount | numeric hygiene QP019, QP020 |
| Revenue | numeric hygiene QP019, QP020 |

The seventh column's spelling, `NumberofCustomers`, is transcribed from the
published template and reproduced deliberately. See
`docs/adr/0002-transcribe-published-artifacts-verbatim.md`.

## CEC-1306A-S2

UDC Retail Rate Description, Schedule 2.

| Column | Rules |
|--------|-------|
| CompanyNumber | QP021 |
| Year | QP010, cross-row QP031 |
| QuarterNumber | QP012 |
| RetailRatClass | none registered yet |
| Description | none registered yet |

This form publishes no column marked with the shared numeric footnote, so
QP019 and QP020 do not apply anywhere on it. The fourth column's spelling,
`RetailRatClass`, is transcribed from the published template and reproduced
deliberately. See ADR 0002.

## CEC-1306B

LSE Quarterly Report.

| Column | Rules |
|--------|-------|
| CompanyNumber | QP021 |
| Year | QP010, cross-row QP031 |
| MonthNumber | QP011, cross-row QP030 |
| UtilityDeliveryCompany | QP022 |
| CustomerGroup | QP015 |
| CountyNumber | QP013, QP024 |
| NumberOfCustomers | numeric hygiene QP019, QP020 |
| SalesAmount | numeric hygiene QP019, QP020 |
| Revenue | numeric hygiene QP019, QP020 |

## CEC-1308B-S1

Gas Utility Deliveries and Revenue, Schedule 1.

| Column | Rules |
|--------|-------|
| CompanyNumber | QP021 |
| Year | QP010, cross-row QP031 |
| MonthNumber | QP011, cross-row QP030 |
| CountyNumber | QP013, QP024 |
| NAICSCode | QP017, QP023, QP018 (unevaluated) |
| RateCode | QP016 |
| NumberOfCustomers | numeric hygiene QP019, QP020 |
| DeliveryVolume | numeric hygiene QP019, QP020 |
| Revenue | numeric hygiene QP019, QP020 |

## CEC-1308C

Gas Retailer Quarterly Report.

| Column | Rules |
|--------|-------|
| CompanyNumber | QP021 |
| Year | QP010, cross-row QP031 |
| Month | QP011, cross-row QP030 |
| CountyNumber | QP013, QP024 |
| CustomerGroup | QP015 |
| NumberOfCustomers | numeric hygiene QP019, QP020 |
| SalesDelivery | numeric hygiene QP019, QP020 |
| Revenue | numeric hygiene QP019, QP020 |

## What the open cells are

Three columns across five templates currently have "none registered yet":
`RateClass` on CEC-1306A Schedule 1, and `RetailRatClass` and `Description` on
Schedule 2. Each sits on the roadmap's Phase 3 reading list with the other
places worth reading again. The outcomes available to each are fixed: a new
rule backed by a transcribed quote, a new registered-but-unevaluated rule
stating why, or a recorded finding that no published text constrains it. All
three outcomes close the cell honestly; none of them invents a check.
