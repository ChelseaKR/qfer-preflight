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
- "none" in a column's rules cell means no rule names the column today. Where
  a cell has been read for and closed, it says so and points at the reading
  note at the bottom of this file.
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
| QP034 | No commas anywhere in the file | unevaluated |

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
| CompanyNumber | QP021, QP033 |
| Year | QP010, cross-row QP031 |
| Month | QP011, cross-row QP030 |
| CountyNumber | QP013, QP024 |
| CustomerType | QP014, QP025 |
| RateClass | none; see the reading note below |
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
| CompanyNumber | QP021, QP033 |
| Year | QP010, cross-row QP031 |
| QuarterNumber | QP012 |
| RetailRatClass | none; see the reading note below |
| Description | none; see the reading note below |

This form publishes no column marked with the shared numeric footnote, so
QP019 and QP020 do not apply anywhere on it. The fourth column's spelling,
`RetailRatClass`, is transcribed from the published template and reproduced
deliberately. See ADR 0002.

## CEC-1306B

LSE Quarterly Report.

| Column | Rules |
|--------|-------|
| CompanyNumber | QP021, QP033 |
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
| CompanyNumber | QP021, QP033 |
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
| CompanyNumber | QP021, QP033 |
| Year | QP010, cross-row QP031 |
| Month | QP011, cross-row QP030 |
| CountyNumber | QP013, QP024 |
| CustomerGroup | QP015 |
| NumberOfCustomers | numeric hygiene QP019, QP020 |
| SalesDelivery | numeric hygiene QP019, QP020 |
| Revenue | numeric hygiene QP019, QP020 |

## What happened to the open cells

The first edition of this map left three cells open: `RateClass` on
CEC-1306A Schedule 1, and `RetailRatClass` and `Description` on Schedule 2.
They have since been read for, in the instruction PDFs this project cites, and
each closes as a finding of nothing mechanical:

- **RateClass (Schedule 1)**: "General level of retail rate class used by the
  reporting UDC. UDCs whose annual peak demand in the last two years is less
  than 200 megawatts (MW) are not required to provide rate class. Column F,
  text data type." A free-text description plus a filing-eligibility rule the
  CSV cannot evidence. No value set, no format, no length.
- **Retail Rate Class (Schedule 2)**: "The general level of rate class used by
  UDC. Column D, text data type." Descriptive only.
- **Description (Schedule 2)**: "Description explaining retail rate classes.
  Column E, text data type." Descriptive only.

"Text data type" constrains the spreadsheet cell, not the characters in it,
so none of these supports a mechanical check. The cells stay marked here so
the reading is not repeated from scratch, and so a future revision of the
instructions that does publish a constraint finds its way to this file.

Two rules grew out of the same reading pass: QP033 now covers every
`CompanyNumber` column, and QP034 registers the workshop deck's comma
sentence as permanently unevaluated.
