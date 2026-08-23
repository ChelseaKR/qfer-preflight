# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Rule identifiers are part of the public interface. A rule identifier is never
renumbered and never reused for a different check. Retiring a rule is a
breaking change and is recorded here.

## [Unreleased]

### Added

- `docs/column-coverage.md`, mapping every column of every published template
  to the rules that touch it, with the three columns no rule names yet marked
  as open cells rather than left implicit. `tests/test_column_coverage.py`
  holds the map against both ends: every profile header must appear in order,
  every identifier named must exist in the registry, every registered rule
  must be named, and no advisory code outside the closed code space may
  appear.
- `docs/ROADMAP.md`, the expansion roadmap: six phases, each gated on the
  same citation bar as the code.
- `docs/source-manifest.md`, recording a retrieval date and a SHA-256 for
  every published document the tool cites: the four instruction PDFs, the five
  CSV templates, the workshop deck, the previous 1306A revision read in
  ADR 0005, and the two Energy Consumption Data Files spreadsheets. A hash
  that stops matching means a cited document changed; the procedure at the top
  of the file begins with "stop", not with refreshing the hash.
  `tests/test_source_manifest.py` refuses a profile-cited document absent from
  the manifest. Dev-time only: nothing at runtime reads it and no test fetches
  anything.

## [0.1.0] - 2026-08-18

First release. An offline pre-submission validator for California Energy
Commission QFER Consumption CSV filings: every finding cites the published
rule it came from, and anything the tool cannot evaluate is reported as not
evaluated rather than passed. An independent utility, not affiliated with,
endorsed by, or approved by the California Energy Commission.

### Added

- Validation engine with a fail-closed contract: unparseable input, an empty
  file, a header that does not match the published template, and a file with
  no data rows all report as an error or as unvalidated, never as a pass.
- Five form profiles covering the QFER Consumption CSV reports: `CEC-1306A-S1`,
  `CEC-1306A-S2`, `CEC-1306B`, `CEC-1308B-S1` and `CEC-1308C`. Header rows are
  transcribed from the published CSV templates.
- Twenty-three implemented rules (QP001 to QP004, QP006, QP007, QP010 to
  QP017, QP019 to QP025, QP030, QP031), each carrying a stable identifier, a
  severity, and a citation to the published document it was derived from.
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
- `--strict`, which also exits non-zero when any rule could not be evaluated or
  any advisory was raised, exercised end to end through the real command line
  entry point.
- Advisories, a separate output channel with its own `ADV-` code space for
  things the reader noticed that no published CEC rule covers: `ADV-BOM`,
  `ADV-LINE-ENDINGS`, `ADV-FORMULA-CELL`, `ADV-HIDDEN-CHARACTER` and
  `ADV-REPEATED-HEADER`. An advisory carries no severity, cites no document,
  and keeps the verdict away from `pass`. It exists because four kinds of
  hostile input previously produced an empty finding list, which reads as a
  clean file. See ADR 0004.
- `tests/test_adversarial_input.py`, a corpus of twenty six deliberately broken
  files, each asserted to produce a report that is neither a pass nor silent.
- Spreadsheet cell references on findings, so a message points at `D2` rather
  than leaving the filer to count commas.
- QP007, an error when a data row is an exact copy of the header row. It is
  registered only for `CEC-1306B` and `CEC-1308C`, the two forms whose
  published "Important Template Notes" sentence says to exclude "extra
  headers". The other three publish the same sentence without those words, and
  there the same row stays an `ADV-REPEATED-HEADER` advisory. See ADR 0007.
- Identical findings are merged into one line carrying the number of rows it
  stands for, the first five of them and the last. A file with the same wrong
  county in 400,000 rows reports one line rather than 400,000. Two findings
  merge only when their rule, their column and their message text all match.
  See ADR 0006.
- A `collapsed` object in the JSON report, stating the merge policy and how
  many findings were merged, and `counts.finding_lines` alongside
  `counts.findings`, so a caller can tell entries from occurrences.
- `tests/test_collapsing.py` and `tests/test_advisory_channel.py`. The first
  holds the merge to terms on which it loses nothing. The second attacks the
  advisory channel on the assumption that an output carrying no citation is
  where an invented check would try to enter.

### Fixed

- A file truncated inside a quoted value is now a QP001 error that blocks every
  other rule. Python's CSV reader accepts an unterminated quoted field without
  complaint, so a file cut in half previously reported its rows and no
  findings.
- Year, Month, Quarter Number and the numeric fields no longer accept non-ASCII
  digits. The patterns used `\d`, which matches every Unicode decimal digit,
  and `int()` converts them, so a Month of `U+FF11` and a Year of
  `U+0662 U+0660 U+0662 U+0665` passed with no finding.
- A CSV parse failure part way through a file now discards the findings
  gathered from the readable prefix. That prefix was not validated either, and
  reporting it alongside a parse error invited reading it as though it had
  been.
- Rows are streamed rather than held in memory all at once, which cuts peak
  memory on a large filing by more than half.
- A CSV parse failure no longer discards what was observed about the file
  itself. A byte order mark and disagreeing line endings are true of the bytes
  whether or not the reader reached the end of them, and one of them may be
  why it did not, so `ADV-BOM` and `ADV-LINE-ENDINGS` now survive a parse
  failure while every finding and every row-level advisory is still discarded.
- `ADV-BOM` is raised before the file is decoded, so a file that is not UTF-8
  still reports the mark on its front, and its wording no longer claims
  anything about a header check that may never have run.
- `ADV-HIDDEN-CHARACTER` no longer claims that no implemented rule constrains
  the column it fired on. That was false of, for example, a NAICS Code that
  satisfied QP017 on length. It now says what is true: nothing published
  addresses an invisible character, and no rule objected to this value.
- A finding can no longer be attributed to a rule the same report lists as
  never applied, and a report is refused if one ever is.

### Changed

- `counts.error`, `counts.warning` and `counts.info` in the JSON report now
  count rows rather than report lines, so a merged finding on 400,000 rows
  counts 400,000. `counts.finding_lines` counts the entries.
- The advisory code space is closed. An advisory cannot be constructed with a
  code outside `ADVISORY_CODES`, and cannot be constructed at all unless its
  own text says the published record does not cover what it noticed.
- Finding messages now say what to change, not only what is wrong. A header
  mismatch reports a difference by difference comparison, names the delimiter
  when the file is not comma separated, and collapses to one sentence when
  every column differs only in whitespace or case. Value messages name
  invisible characters and their code points, give the published legend for a
  code set, suggest the corrected numeric value, and distinguish a value that
  is out of range from one that is not a number at all.
- Tests for the release workflow's fail-closed behaviour. The guard that stops
  the job when `.github/allowed_signers` names no principal is lifted out of
  the workflow file and run in a real shell, against a missing file, an empty
  file and a comment-only file, and all three stop the job. The signer list is
  committed and names the maintainer's release-signing key, and the workflow
  re-runs `make verify` at the exact tagged commit and refuses a tag whose
  name disagrees with the package version.
- A "Releasing" section in `CONTRIBUTING.md` documenting how a release is cut
  and what the workflow refuses.

### Notes

- `CEC-1304` power plant generation reporting is deliberately out of scope. It
  is filed outside the CSV portal and publishes no CSV template. `CEC-1306A`
  Schedule 3 and `CEC-1308B` Schedule 2 are out of scope for the same reason:
  both go by SFTP and their templates are only available on request.
- The CEC "Valid NAICS codes" list is referenced by the instructions but is not
  published at a retrievable URL, so QP018 checks nothing and says so. The
  search for a published copy is now closed rather than unfinished.
  `ecdms.energy.ca.gov` does not resolve because that system is retired, and
  its successor, the Energy Consumption Data Files page, was read on
  2026-08-17 and publishes no NAICS code list, no customer type list and no
  rate class list.
- ADR 0008 records a second CEC dataset corroborating the county code set: 58
  distinct county numbers, 1 through 58, all unpadded. It leaves QP024 a
  warning rather than making padding an error, because no published source
  says a filer must not pad, the file stores county numbers as spreadsheet
  numbers which cannot carry a leading zero anyway, and it is aggregate
  consumption reporting rather than a QFER filing. No rule, severity or code
  set changed.
- ADR 0003 records what the tool does when two published Commission documents
  disagree: it declines to report an error and reports the disagreement.
- ADR 0005 records a re-examination of the Customer Type `O` call. It holds.
  The July 2025 instructions did not withdraw `O`: the previous published
  revision listed only D and B, so the revision's net change was to add C, and
  `O` has never appeared in any revision of the instructions to be removed
  from. No published text since says it is not accepted.

[Unreleased]: https://github.com/ChelseaKR/qfer-preflight/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChelseaKR/qfer-preflight/releases/tag/v0.1.0
