# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Rule identifiers are part of the public interface. A rule identifier is never
renumbered and never reused for a different check. Retiring a rule is a
breaking change and is recorded here.

## [Unreleased]

### Added

- Validation engine with a fail-closed contract: unparseable input, an empty
  file, a header that does not match the published template, and a file with
  no data rows all report as an error or as unvalidated, never as a pass.
- Five form profiles covering the QFER Consumption CSV reports: `CEC-1306A-S1`,
  `CEC-1306A-S2`, `CEC-1306B`, `CEC-1308B-S1` and `CEC-1308C`. Header rows are
  transcribed from the published CSV templates.
- Twenty implemented rules (QP001 to QP004, QP006, QP010 to QP017, QP019 to
  QP023, QP030, QP031), each carrying a stable identifier, a severity, and a
  citation to the published document it was derived from.
- Three rules registered as explicitly unimplemented (QP005, QP018, QP032),
  reported as unevaluated on every run with a stated reason.
- Published code sets transcribed from CEC instruction documents: county
  numbers, residential classification codes, CEC custom classification codes,
  gas rate codes, customer types, customer groups and valid UDC values.
- `check`, `rules` and `profiles` commands, with text and JSON output.
- `--strict`, which also exits non-zero when any rule could not be evaluated.

### Notes

- `CEC-1304` power plant generation reporting is deliberately out of scope. It
  is filed outside the CSV portal and publishes no CSV template.
- The CEC "Valid NAICS codes" list is referenced by the instructions but is not
  published at a retrievable URL, so QP018 checks nothing and says so.

[Unreleased]: https://github.com/ChelseaKR/qfer-preflight/commits/main
