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
- Twenty-two implemented rules (QP001 to QP004, QP006, QP010 to QP017, QP019
  to QP025, QP030, QP031), each carrying a stable identifier, a severity, and a
  citation to the published document it was derived from.
- QP024, a warning that a County Number is written zero padded, for example
  `07`. This replaces an error the tool used to report on no published
  authority. See ADR 0003.
- QP025, an informational note that Customer Type `O` is listed as valid by the
  DSP workshop deck and is absent from the instructions. This replaces an error
  the tool used to report, which would have been a false alarm for the one
  filer entitled to use the value. See ADR 0003.
- The DSP workshop slide deck (June 24, 2025) as a third cited source,
  alongside the instruction PDFs and the CSV templates.
- Three rules registered as explicitly unimplemented (QP005, QP018, QP032),
  reported as unevaluated on every run with a stated reason.
- Published code sets transcribed from CEC instruction documents: county
  numbers, residential classification codes, CEC custom classification codes,
  gas rate codes, customer types, customer groups and valid UDC values.
- `check`, `rules` and `profiles` commands, with text and JSON output.
- `--strict`, which also exits non-zero when any rule could not be evaluated,
  exercised end to end through the real command line entry point.
- Tests for the release workflow's fail-closed behaviour. The guard that stops
  the job when `RELEASE_ALLOWED_SIGNERS` is unset is lifted out of the workflow
  file and run in a real shell, unset and blank, and both stop the job.
- A "Releasing" section in `CONTRIBUTING.md` documenting the one manual setup
  step a first release needs.

### Notes

- `CEC-1304` power plant generation reporting is deliberately out of scope. It
  is filed outside the CSV portal and publishes no CSV template. `CEC-1306A`
  Schedule 3 and `CEC-1308B` Schedule 2 are out of scope for the same reason:
  both go by SFTP and their templates are only available on request.
- The CEC "Valid NAICS codes" list is referenced by the instructions but is not
  published at a retrievable URL, so QP018 checks nothing and says so.
- ADR 0003 records what the tool does when two published Commission documents
  disagree: it declines to report an error and reports the disagreement.

[Unreleased]: https://github.com/ChelseaKR/qfer-preflight/commits/main
