# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Rule identifiers are part of the public interface. A rule identifier is never
renumbered and never reused for a different check. Retiring a rule is a
breaking change and is recorded here.

## [Unreleased]

### Added

- **`check --naics-list PATH`, so QP018 can reach a verdict for a filer who holds
  the list it needs.** The Commission's "Valid NAICS codes" list is published at no
  URL this project can retrieve and staff have said it will not be, so QP018 has
  been registered, unevaluated, and reported on every run. It lives in the data
  dictionary on the portal app landing pages. A filer who has that document can now
  hand the codes to this tool instead of forking it.

  **This project still ships no list and fetches none.** The file is read from the
  caller's disk, once, and no copy of it is written into any report: the Commission
  declined to publish that list, and a report is a document a filer forwards, so a
  hint names a transform of the filing's own value or counts how many codes share a
  prefix, and stops there.

  **The report says what the rule rested on.** Its header block states that QP018
  was evaluated against a caller-supplied list rather than a published one and names
  the file's path as given, its SHA-256, its distinct code count and its line count;
  `--format json` carries the same under `code_lists` (schema minor version 1.2, an
  optional field, `report-v1.schema.json` unchanged in its major version). Every
  QP018 finding repeats the path and the digest, because a reader of the report is
  not necessarily the person who ran it.

  **Three states, not two.** No list, a list that was refused, and a list that was
  read. The first two both leave QP018 unevaluated and they carry different reasons,
  so a filer who mistyped a path is told about their typo rather than about the
  Commission's publication practice. Reading fails closed on an unreadable file, a
  byte order mark, non-UTF-8 bytes, an empty file, and any line that is not exactly
  six characters once its line ending is stripped. Nothing is trimmed or corrected:
  one trailing space turns a valid code into one that matches nothing, and the QP018
  error that followed would name a correct filing as wrong.

  **Without the flag nothing moved.** The report is byte for byte what this tool has
  always written, in both renderings, and a test compares them as bytes.
  `qfer-preflight rules` still prints QP018 as not implemented, because the registry
  describes what this project ships. ADR 0011 records why this is consistent with
  ADR 0009's refusal to ground a finding in material a reader cannot open, and where
  the mechanism stops: QP005, QP032 and QP034 are unevaluated for reasons no file a
  caller could supply would settle.

- A source watcher, so the manifest's procedure stops depending on somebody
  remembering it. `scripts/watch_sources.py` re-fetches every document in
  `docs/source-manifest.md`, compares digests, and names the rules whose citations
  point into anything that moved; `.github/workflows/source-watch.yml` runs it on the
  8th of February, May, August and November, a week before each filing deadline, and
  opens a pull request on drift. **The pull request updates nothing** -- a changed hash
  means a rule may be quoting superseded text, and `source-manifest.md` already says
  that deciding what that means is a person's ADR.

  Four outcomes, kept apart on purpose: `unchanged`, `drifted`, `error` and
  `not-checked`. **`error` is not `unchanged`**, and a run that could not fetch a
  document exits 2 rather than reporting no drift, because a watcher that said "no
  drift" while the Commission's web server was down would be a green light nobody had
  earned.

  `not-checked` exists because the first version of this script did not have it and
  committed the defect it was written to prevent: `--dry-run` printed
  `13 unchanged` and `Every cited document re-hashes as recorded` having made no
  request at all. A dry run now reports every entry as not checked and says in terms
  that it establishes nothing about drift, and the workflow's offline selftest asserts
  that the dry-run summary claims zero unchanged.

  Run live against energy.ca.gov on 2026-09-07: **13 documents, 13 unchanged, 0
  drifted, 0 could not be checked.** Every cited document still hashes as this
  repository records it.

- A findings table, for the spreadsheet the filing came out of.
  `check --format findings-csv` and `--format findings-jsonl` write one line per
  **row and finding** -- `row, column, rule_id, severity, cell, message` -- with
  nothing merged and nothing withheld, sorted by row then rule, file-level findings
  first, advisories carried with an empty severity because no published rule covers
  them. The report merges an identical finding across rows and has to; a filer
  fixing four hundred thousand rows needs the ungrouped view beside their data.

  **The rows are emitted during the single pass and are never rebuilt from the
  report.** That is the design constraint rather than an implementation detail: a
  merged `Finding` keeps `occurrences`, the first row, the first five `example_rows`
  and the last, so a table expanded from one would print five lines under a header
  claiming a line per row. A filer would sort it, fix what it listed, re-run and
  find the filing still rejected. `engine.FindingSink` is called once per
  occurrence, the renderer never sees a `Finding`, and
  `test_a_repeated_finding_produces_one_line_per_row_not_one_per_group` pins it over
  a forty-row filing -- a fixture wide enough that merging genuinely happens, because
  the existing dirty fixture merges nothing and would have passed either way.

  The table states in its own header that it is not the report, and carries the
  run's `status`. A zero-line table is not a clean bill, and the report remains the
  only output that says which rules were never evaluated.

  Every CSV field is neutralised against spreadsheet formula injection, whitespace
  considered, because a spreadsheet strips leading whitespace before deciding
  whether it is looking at a formula. On the messages this tool emits today no field
  begins with a formula leader, so this is defence in depth rather than a live
  exploit; it is tested over synthetic hostile rows rather than real findings,
  because a fixture built from real findings would sit where the failure is
  impossible and would pass whether the neutraliser worked or not. `--findings-bom`
  adds the byte order mark Excel needs. A batch writes one table per input through
  `--findings-dir` and refuses to concatenate them, because a concatenated table
  cannot be sorted without interleaving two filings whose row numbers mean different
  things.

  The GitHub Action deliberately does **not** offer these two formats. Its contract
  is a report file plus an optional SARIF upload, and an input that made
  `report-path` name something that is not a report would quietly weaken the one
  promise the action exists to keep.

- A publish path, `.github/workflows/publish-pypi.yml`, and a README section
  that says what is installable today. `release.yml` made a GitHub release and
  stopped there: there was no way to get this tool onto a package index, and
  the README's Quickstart opened with `uv sync` without saying that a clone was
  the only install there is. A reader who reached for `pip install
  qfer-preflight` got nothing, and nothing in the repository told them why.

  The new workflow is the shape `ca-tariff-parse` and `outcome-receipts`
  already use here: dispatched by hand, never on a push, taking a tag
  `release.yml` has already published; the allowed-signers guard first, then a
  stable-SemVer check, the tag object type, `git verify-tag`, ancestry on
  `main`, and a `gh release view` that refuses a tag no release was cut from;
  a build at the verified commit whose filenames must carry the tag's own
  version; and an upload job that never checks the repository out and holds
  nothing but an OIDC token. No PyPI API token is stored anywhere and none is
  wanted.

  Nothing publishes on merge and nothing publishes on a tag. **The workflow is
  inert until PyPI Trusted Publishing is registered, which is a web-UI action
  only the project owner can take, and until she dispatches it.** The five
  values that registration needs are in the workflow header and in the
  README's new "Release and versioning" section, because a job that fails
  closed with a trusted-publisher error and no instructions is a job nobody can
  act on. Ten properties of the new workflow are held by
  `tests/test_release_workflow.py`, and `tests/test_ci_action.py`'s
  every-workflow-is-accounted-for check required it to be named and given a
  reason before it could exist at all.

- An `evaluation` ledger in every report: one entry per rule and per column it
  touches, saying how many rows the rule was offered, how many it judged, how
  many its own published applicability does not reach, and how many an earlier
  rule left unreadable, with that rule named. `rules_evaluated` lists
  identifiers and `docs/column-coverage.md` maps columns to rules in the
  abstract; neither says what happened on the file in front of you, and a rule
  can be listed as evaluated, correctly, having read every row and judged none
  of them. That is the next version of `Findings: none` reading as clean.
- Zero judged is published as zero with its reason attached. `zero_reason` is
  one of `no_applicable_rows`, `blocked_by` or `column_absent`, is present
  exactly when nothing was judged and never otherwise, and `evaluated` beside it
  separates a rule that ran and judged nothing from one that never ran. The four
  counts have to sum to what the rule was offered and `LedgerEntry` refuses an
  entry where they do not, because a ledger that has quietly lost rows reports
  them as checked.
- Five places where a rule declines to reach a verdict are now recorded as
  exemptions rather than passing silently for having produced no finding: QP023
  on a NAICS code that is not a residential classification code, QP033 on a
  blank company number, QP020 on a cell holding the placeholder QP019 covers,
  QP013 on a zero-padded county and QP014 on a Customer Type the instructions
  and the workshop deck disagree about. The last two are ADR 0003 and ADR 0005
  in the ledger rather than only in the message text.
- `--strict-ledger`, which exits non-zero when any rule judged no rows on a
  column this form carries, and names them on stderr. A clean filing can fail
  it: on `CEC-1308B-S1` a file of ordinary six-digit NAICS codes leaves QP023
  with nothing in its published scope, and the flag exists to say so.
- Report schema minor revision 1.1. `evaluation` is optional rather than
  required, so a report written by an earlier version is still a valid version 1
  report; `schema_version` stays 1. The minor number is recorded as
  `minorVersion` in `docs/schemas/report-v1.schema.json`, with its history, and
  pinned by `tests/test_report_schema.py`.
- `tests/test_evaluation_ledger.py` derives the ledger's rule to column map from
  `docs/column-coverage.md`, in both directions, so a rule the registry runs and
  the ledger never counts fails the suite rather than reporting zero forever.
- A supported Python API. `qfer_preflight.validate(path_or_bytes,
  profile=None)` returns a `Report`; `detect_profile`, `profiles` and `rules`
  expose detection and the registry; `Report` gains `to_json`, `to_text` and
  `to_sarif`, which produce byte-identical output to the matching
  `check --format`, because they call the same renderers rather than a second
  copy. `__all__` is the supported surface and the README states the SemVer
  policy for it, matching the report schema's: additive is minor, removal or
  retyping is major. Until now a Python consumer imported `engine`, which is
  private and free to move.

  Three properties are asserted rather than intended, in
  `tests/test_public_api.py`. Fail-closed travels with the API: a filing that
  could not be read comes back as a `Report` whose verdict is not `pass`,
  rather than as an exception a caller has to interpret. Detection refuses
  instead of guessing, raising `ProfileDetectionError` with the near misses
  named, and a test forbids the near misses ever becoming a fallback.
  Importing the package opens no data file and imports no argument parser,
  checked with an audit hook in a fresh interpreter.

  The header scan and profile detection moved out of `cli.py` into
  `detect.py`, and the unbound rule listing into `rules.all_rules`, so the
  command line and the API run one implementation instead of two that agree
  today. No CLI behaviour or output changes.

- `qfer-preflight explain <RULE_OR_ADV_CODE>`, with `--profile`, `--value` and
  `--format json`. A finding names the rule and the offending value; until now the
  filer who wanted to know why had `rules --profile`, which prints the whole
  registry, and the filer guide, which is written per form rather than per rule.
  `explain` prints one rule: the verbatim quote as transcribed with its document
  and locator, resolved through `bind` so that a rule whose text differs per form
  shows the text for the form asked about (ADR 0007); the severity; and for a
  registered unevaluated rule its reason and the promotion condition it states.
  An advisory code prints that no published rule covers what it reports, and why
  the code space is closed (ADR 0004).
- `--value` runs `engine.check_one_cell`, a new public entry point that places one
  value in one column of an otherwise empty row and runs the engine's real row
  checks over it. The message a filer reads is therefore the message the tool
  produces rather than a second account of it that agrees today and drifts later.
  No mapping from rule to column is maintained: the value is tried in each column
  and the columns the rule reads are the columns it fires on. `explain QP024
  --value 07` prints the published county table's entry for `7`, the workshop
  deck quote at slide 19 rule 6, and the engine's own sentence saying that no
  published source calls the padded form an error, so it is a warning.
- Two absences are stated rather than left blank, which is the failure this
  project exists to prevent. The instructions print example values for some
  fields and none of that text is transcribed here, so the published-example
  section says no example is recorded rather than printing nothing and letting
  the blank read as the instructions giving none. And `--value` reaches only the
  rules that read a cell: a structural rule reads the submission as an object and
  a cross-row rule reads a column down the file, so for those it says one cell
  cannot exercise the rule instead of reporting that nothing was found, which
  would say a value passed a check that never ran. The rule's own `tags` decide
  which, `rule_kind` refuses a rule whose tags name no kind rather than assuming
  one, and `tests/test_explain.py` pins the vocabulary against the registry.
- `docs/filer-guide.md` gains an `explain` command in each of the five form
  sections, and `tests/test_filer_guide.py` now runs every command the guide
  prints, checks that one exists per form, and checks that each names a rule that
  applies to the form it is shown under. The guide's CSV examples were already
  executed; its command lines were not, so a command could have named a rule that
  no longer exists and the page would have gone on telling a filer to run it.

- A status beside every item in `docs/ROADMAP.md`, and `tests/test_roadmap_claims.py`
  to hold it there. Phases 1 and 2 were built and the document still described them as
  forward work, which is how issues #33 to #40 came to be filed for finished work. Each
  phase item now carries `**Status: shipped.**` with the evidence that proves it, or
  `**Status: continuing.**` for growth work with no state to reach, and the `Sequencing`
  table gained a matching `Status` column. The test derives the claims rather than
  trusting them: a `shipped` item must name evidence, every path it names must exist,
  every `path::symbol` must appear in that file, a shipped phase may not sit above an
  unshipped item, and the table must agree with the item it points at.
- The same test reads the figures the roadmap states out of the artifacts they describe,
  because four of them had drifted and nothing was reading them. "Twenty-three
  implemented rules" against a registry of twenty four; "three registered as permanently
  unevaluated" against four, with QP034 missing from the list beside it; "an adversarial
  corpus of twenty six hostile files" against twenty seven, the same drift
  `tests/test_readme_claims.py` had already corrected in the README; and "Nine ADRs"
  three hundred lines above this document's own "The ten that exist", which was right.
  All four are corrected here, and each is now compared against the registry, the corpus,
  `docs/adr/` or `pyproject.toml`. The corpus figure is also swept for across the whole
  document, so a third sentence inventing a third number fails rather than passing
  unread.

- `docs/adr/0010-the-unallocated-rule-identifiers.md`, which answers a question
  the repository had left open: the rule sequence skips QP008, QP009 and QP026
  through QP029, next to a standing promise that identifiers are permanent and
  are never renumbered or reused, and nothing said whether those six were
  withdrawn, lost, or never written. Every commit, branch, tag and dangling
  object in the history was searched for the six strings and none of them has
  ever appeared, so no rule was withdrawn and none was lost. The gaps line up
  with the registry's three sections, each of which began on a round number in
  the first commit and was left with headroom above its last rule. Why it was
  spaced that way is not recorded anywhere, and the ADR says that instead of
  supplying a reason it cannot source. The six stay unallocated, and new rules
  go on taking the next unused identifier above the highest one.
- Two tests in `tests/test_rules.py` that hold the ADR and the registry
  together: one derives the unallocated set from `RULE_SPECS` and compares it
  to the six recorded, the other checks the ADR names each of them. Filling a
  gap or opening a new one now fails the build until the record is amended.

- `docs/filer-guide.md`, a guide for the person doing the filing rather than
  the person reading the code. A section per form carrying the published
  header, a synthetic worked example, and the outcome the tool reports for
  it; what each exit code means and how `1` and `2` differ; when `--strict`
  is the right setting and why it fails on every file; what an unevaluated
  rule and an advisory each mean for the decision to submit; how to read the
  cell reference in a finding; and a worked failing run showing all three
  severities, including why the zero padded County Number is a warning the
  project knows to be more lenient than the portal.
- `tests/test_filer_guide.py`, which stops the guide from claiming behaviour
  the tool does not have. Every CSV block is extracted, matched against the
  transcribed template headers, written to disk and run through the same
  entry point a filer's run uses. The status, the number of rules evaluated,
  the exact list of unevaluated rules, the advisory count and the exit code
  the guide states are compared against the real ones, plain and under
  `--strict`. Prose is not trusted either: every `QP` identifier and every
  `ADV-` code named in the guide or the glossary must exist in the registry
  and in the closed advisory code space.
- `docs/glossary.md`, covering the two vocabularies a report mixes. The
  Commission's terms, each quoted from the document that publishes it with
  the section named: QFER from the program page title, DSP, UDC and LSE from
  the instruction documents, and TEOR and UEG from the CEC-1308C Customer
  Group list. NAICS is the entry that says what the project does when a term
  is not defined in its sources: the four instruction PDFs and the workshop
  deck use the abbreviation without ever expanding it, so the glossary states
  that and supplies no expansion of its own. The tool's terms are defined
  alongside them, including the collision worth knowing about, that a warning
  here means the published record does not support calling a value wrong,
  which is not what the portal means by the word.
- `CONTRIBUTING.md` gains two recipes: how to propose a rule without writing
  one, where a proposal without a transcribed quote is declined however
  sensible the check sounds, and how to report a value the tool rejects that
  a published document calls valid, which is the highest-value defect this
  project can receive because it goes straight at ADR 0003. The second names
  the two outcomes, a plain misreading defect or a documented disagreement
  reported at warning severity, and repeats that correspondence never moves a
  severity.
- Two CI surfaces, so a filer who keeps quarterly CSVs in version control runs
  the same offline check on every push. `action.yml` is a composite GitHub
  Action taking `paths`, `profile`, `strict`, `format` and `upload-sarif`, and
  reporting `exit-code` and `report-path`. `.pre-commit-hooks.yaml` publishes a
  `qfer-preflight` hook that runs `qfer-preflight check` over staged CSV files.
  Both keep the exit code contract unchanged, and both detect the profile from
  each header, so a folder holding five forms configures nothing.
- The action installs nothing and consults no package index. A composite action
  is checked out at the reference the caller pins and the validator has no
  runtime dependencies, so the action puts that checkout's `src` on PYTHONPATH
  and runs it: the bytes that run are the bytes the pinned reference names, with
  no index in between to trust. `tests/test_ci_action.py` holds the empty
  runtime dependency set that makes this legal, and holds the action's Python
  floor against `requires-python`.
- Nothing in the action can turn a failed validation into a green job. There is
  no `continue-on-error`, no `|| true` and no trailing `exit 0` anywhere in it,
  the exit code is recorded rather than discarded, and the final step refuses an
  empty or non numeric recorded code because a run that reached no verdict
  validated nothing. Pointed at an empty directory, at a directory holding no
  CSV, or at a header matching no published template, the job fails.
  `.github/workflows/action-selftest.yml` runs the action over the repository's
  own fixtures for ten cases and compares each job outcome against the one the
  case states, and `tests/test_ci_action.py` puts every exit code the matrix
  claims through the CLI so those constants cannot go stale unnoticed.
- A "Running it in CI" section in `docs/filer-guide.md`, with a workflow
  example, a `repos:` entry, and the two limits worth knowing before adopting
  either: the action cannot verify the signature on its own tag, because an
  action checkout has no history to verify against, so the guide shows how to
  run `git verify-tag` against a clone instead; and an uploaded SARIF names each
  input by base name, so code scanning attaches alerts to lines only when the
  filing sits at the repository root.

### Fixed

- **The batch SARIF rendering recorded a refusal only where no consumer reads it.**
  An input the tool could not process gets a run of its own, and that run carried its
  reason in `run.properties.problem` alone. A machine reading the log saw an
  unsuccessful invocation, an empty `results` array, no `toolExecutionNotifications`
  and no catalogued notification descriptor, with nothing in the standard saying the
  filing was never validated or why. That is the same extension bag, and the same
  mistake, the single-report rendering was corrected for: the fix that gave every
  unevaluated rule a notification never reached `batch_to_sarif`, so **the run that
  checked nothing said less, in the places a consumer looks, than the run that checked
  almost everything.** Measured on a two-input batch of `1306a_s1_clean.csv` and
  `empty.csv`: the validated run carried five notifications against zero results, and
  the never-validated run carried none.
  Such a run now carries one `toolExecutionNotification` at level `error`, naming the
  input and repeating the native reason, with its descriptor catalogued in
  `tool.driver.notifications`. `error` rather than the `warning` an unevaluated rule
  carries, because a run that reached a verdict without checking everything is not the
  same condition as an input for which no analysis ran at all.
  `executionSuccessful` stays `false` and `properties.problem` stays, since nothing is
  dropped for being said in two places.

- Commits reached `main` with no CI verdict at all. `ci.yml` and
  `security.yml` keyed their concurrency group on `github.ref`, which puts
  every push to `main` into one group, and cancelled in progress runs
  unconditionally, so each merge discarded the run belonging to the commit
  before it. Measured on 2026-09-06 over the whole run history: `62ce09d`
  carries no check runs at all, `ac467a1` carries only cancelled ones, and
  `ee7b346` carries four cancelled out of five, all three from pull requests
  merged thirteen seconds apart. A gate whose result was thrown away is not
  distinguishable afterwards from a gate that never ran. Turning cancellation
  off would not have repaired it, because a concurrency group holds at most one
  pending run and a third arrival evicts the second as silently. The group now
  varies with the commit on a push, so no two `main` runs ever contend, while a
  pull request keeps its ref and keeps cancelling superseded runs, which is
  what that setting was added for. `tests/test_gate_parity.py` holds both
  workflows to it.

- Profile detection refused a whole filing, with a false explanation, when a
  valid header was followed by an invalid UTF-8 byte anywhere in the first
  8 KB. Detection was documented everywhere as reading the header row only,
  and did not: opening a text handle makes `TextIOWrapper` decode a whole
  read-ahead block to satisfy one `next()`, so a `UnicodeDecodeError` raised
  by bytes far past the header landed in the handler that reports on the first
  row. The filer was sent to inspect a header that is byte perfect, and got no
  report at all, while the identical defect a few thousand bytes further into
  the file detected fine and got a report naming the offending byte exactly.
  Which of the two outcomes a filing received depended only on where its bad
  byte fell relative to a window nothing documents, on stderr in single-file
  mode and as the entry's `problem` in batch mode. Detection now reads the
  bytes of the first CSV record and stops, so a decode failure caught there is
  genuinely about the header and everything past it is left to the reader,
  which is fail-closed and names the byte. The record end is found on undecoded
  bytes, which is safe because the quotation mark and the two line break
  characters are ASCII and no ASCII byte appears inside a multi-byte UTF-8
  sequence. `tests/test_detect.py` pins the outcome at seven offsets bracketing
  the old 8 KB boundary, in single-file and batch mode, checks that detection
  and `--profile` now produce the same report, and holds the record scan
  against what `csv` treats as the end of a record, including a line break
  inside a quoted field, across every chunk size.

- The streaming reader named the wrong byte, and called a valid byte invalid,
  when a bad UTF-8 sequence straddled a chunk boundary. The incremental
  decoder decodes its own leftover buffer followed by the new chunk, so its
  error indices are measured from one to three bytes before the chunk begins
  whenever the previous chunk ended on an incomplete but so far valid
  character. Only the byte order mark's shift was undone, so the offset and
  the byte both landed exactly `len(buffer)` late: the reported offset pointed
  past the real offender and the byte quoted back to the filer was a byte that
  is fine. QP001 is fail-closed, so when it fires that one sentence is the
  whole actionable output, and at the shipped 1 MiB chunk size the case arises
  in any filing over 1 MiB. Both bases are now undone together, and the
  offending byte is read out of whichever of the two the index falls in. The
  suite had been green because `tests/test_streaming.py` compared the chunked
  scanner only against itself, through `validate_path` versus `validate_bytes`,
  which both route through the same chunked reader. It now compares the
  reported offset and byte against a whole-file `bytes.decode("utf-8-sig")`,
  across five bad sequences chosen for how much of a character is held at the
  boundary, with and without a byte order mark, at every chunk size from one
  byte upward, plus the measured 1 MiB case at the shipped chunk size with
  nothing monkeypatched.

- `scripts/bench_large_file.py` printed a peak resident set size 1024 times
  too small on Linux. `ru_maxrss` is in bytes on macOS and the BSDs and in
  kilobytes on Linux, which `getrusage(2)` states and the reading itself does
  not reveal, and the script divided by 1024 * 1024 on every platform. Linux
  is the only platform the project runs automatically, since every job in
  `ci.yml`, `release.yml` and `security.yml` is `runs-on: ubuntu-latest`, and
  too small is the flattering direction for a figure `README.md` cites as the
  evidence that memory stays bounded. At one decimal place the error did not
  even read as an error: an ordinary run that reports `27.0 MiB` here printed
  `0.0 MiB` there, which looks like a broken harness rather than a wrong
  unit. The conversion is now a named function taking the platform, so the
  unit rule is stated once and can be tested from both sides, and
  `tests/test_bench_harness.py` holds it there: the same real memory has to
  produce the same MiB figure whichever unit it arrives in, the superseded
  arithmetic is pinned as the 0.0 it produced, and a live reading from the
  test process has to land above 1 MiB, which the 1024x error cannot reach.

- QP033's quote for `CEC-1306A-S2` was Schedule 1's wording, under a comment
  claiming the document reprints the same field definition in its Schedule 2
  section. It does not. The "CEC-1306A Schedule 2 Instructions" section of
  the cited PDF publishes its own Company Number definition, which adds "This
  is the same Company Number found in CEC-1306A Schedule 1." and words the
  leading zero clause as "numeric data type unless your Company Number
  contains a leading zero, in which case, text data type" rather than
  Schedule 1's "or text data type if Company Number begins with leading
  zero". Found by reading the profile's quotes against the live PDF, page 4,
  on 2026-08-29. The check itself was right both ways; the transcription is
  what this project promises, and it was wrong. The S2 entry now carries the
  Schedule 2 section's own wording.
- SARIF `result.ruleIndex` carried the rule's identifier instead of its
  position. SARIF 2.1.0 types the field as an integer, the zero-based index
  into `runs[].tool.driver.rules`, and this rendering emitted a string such as
  `"qfer/QP010"`, which is what `ruleId` already says. A consumer resolving a
  result to its rule by index found a string where the standard promises a
  number. Shipped in 0.2.0 and reported from outside the project. The index is
  now recorded as the array position at the moment each rule is appended, so
  it is correct by construction rather than by a counter kept in step by hand.
  Two tests assert the round trip, that indexing into the rules array lands on
  the rule the result names, for findings and for advisories alike; a type
  check alone would have accepted an integer pointing at the wrong entry.
- The SARIF rendering reported an incompletely checked filing as a clean one.
  ADR 0001 makes a spotless submission report `unvalidated`, because every
  profile registers rules that cannot be evaluated from published text, and
  the text rendering prints that in capitals. This rendering carried it only
  in `run.properties.status` and `run.properties.rulesNotEvaluated`, which are
  extension properties no SARIF consumer reads, so the same run reached a
  machine as an empty `results` array beside `executionSuccessful: true`. A
  file whose bytes could not be decoded was worse: one QP001 result, and the
  twenty two rules that were never applied because of it stated nowhere a
  reader would look. That is the false clean ADR 0001 exists to prevent,
  reintroduced by a derived surface. Every unevaluated rule now emits a
  warning-level `invocation.toolExecutionNotifications` entry carrying its
  reason, catalogued in `tool.driver.notifications`, and a report that is not
  `pass` emits one more carrying the same verdict sentence the text rendering
  prints. `executionSuccessful` stays true: the invocation did complete and
  did reach a verdict, and what it could not check is what the notifications
  say. The verdict sentence now has one definition, `unvalidated_sentence`,
  used by both renderings, so they cannot drift into phrasing it differently.
  Nothing about `results`, severities, citations or the native report changed.
- `tests/test_sarif.py` had pinned the unevaluated rules to
  `run.properties.rulesNotEvaluated` and called that fidelity. Surviving into
  an extension bag no consumer reads is indistinguishable from being dropped,
  for every reader the rendering exists to serve, so the test was asserting
  the defect. It now holds them to the notifications, in both directions:
  every unevaluated rule has a notification and every notification names an
  unevaluated rule.
- The QP001 message for a file holding nothing but a byte order mark read
  "byte order mark , the bytes EF BB BF", with a space in front of the comma.
  It was the hole left by an optional `{tail}` interpolation that stopped
  varying and was removed while the space in front of it stayed, next to a
  `.replace("  ", " ")` that went on running over a literal with no doubled
  space in it. The ADV-BOM advisory printed directly beneath it words the same
  clause correctly, so the two messages disagreed about their own punctuation.
  `tests/test_streaming.py` had pinned the defective spelling. It now walks
  every message the reader can produce for a file it refuses and rejects a
  space before any of `, . ; :`, so the next hole of this shape is caught
  wherever it opens rather than only where this one was.

## [0.2.0] - 2026-08-26

### Added

- QP033, an error when a Company Number is not written as digits alone. All
  four instruction documents publish the column as numeric data type,
  allowing text only so a leading zero survives; CEC-1306B adds that
  "Non-numeric characters (e.g., dashes) must be removed", and the workshop
  deck's formatting rule 4 names Company Number among the fields that may
  not carry blank cells or non-numeric characters. A blank cell stays a
  QP021 presence finding rather than piling on.
- QP034, registered and permanently unevaluated: the workshop deck's "Do not
  include commas anywhere in the file". Taken literally it rejects every CSV
  the portal itself defines; any narrower reading would be interpretation.
  Its reason text says so, and points at QP019, QP020 and QP033 for what is
  mechanical in the same sentence.
- `--format sarif` on `check`: SARIF 2.1.0, one run per input in batch mode.
  Findings become results with severities mapped to levels; merged findings
  stay one result naming its occurrences; cited rules carry their citation
  and quote; advisories remain results of level none under rule entries
  flagged advisory:true whose description states no published CEC document
  stands behind them. Status, unevaluated rules with their reasons and the
  merge policy survive in run.properties.
- The column coverage map closed its three open cells after reading:
  `RateClass`, `RetailRatClass` and `Description` publish free-text
  descriptions and, in one case, a filing-eligibility threshold the CSV
  cannot evidence. No mechanical constraint exists to check, and the map now
  records the reading instead of leaving the cells silent.
- Batch mode. `check` now accepts several paths and directories, in name
  order. Each input produces its own complete report; findings never merge
  across inputs and no count aggregates across them. JSON output becomes a
  batch envelope, published as `docs/schemas/report-batch-v1.schema.json`,
  embedding each single-report document unchanged; the suite cross-validates
  every embedded report against the v1 report schema and asserts byte parity
  with validating each file alone. Inputs that cannot be processed appear as
  `not-validated` entries carrying their reason, never silently dropped.
  Aggregate exit codes: findings outrank usage problems, so a run containing
  both a failed filing and an unreadable path exits `1`, not `2`.
- Profile detection. `check --profile` is now optional: when it is omitted,
  the tool reads the file's header row and proceeds only on an exact,
  unambiguous match against the published templates, typos included. No
  match, several matches, an unreadable file and an empty file are all usage
  errors that say so, never guesses. Naming `--profile` explicitly keeps the
  old behaviour, including validating a file whose header is wrong.
- `docs/schemas/report-v1.schema.json`, a published JSON Schema for the
  `--format json` report, with the compatibility policy written into it:
  additive fields are minor, removals and type changes are breaking. Reports
  now carry a `schema_version` field, currently 1.
  `tests/test_report_schema.py` validates real reports for every profile,
  merged findings, advisories, header mismatches and unreadable bytes against
  the schema, so the two sides cannot drift in either direction.
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

### Changed

- `validate_path` no longer holds the filing in memory. It walks the bytes
  once in bounded chunks, collecting the facts a report needs (the hash, the
  byte order mark, line-ending counts, emptiness, an unterminated-quote flag,
  and the exact offset of any invalid UTF-8), then streams rows to the
  checker off disk. Peak memory now grows with the longest row rather than
  with the file; a synthesized 400,000-row filing validates at roughly 27 MiB
  of resident memory in about two seconds. `validate_bytes` runs through the
  same implementation, so the two entrances cannot disagree;
  `tests/test_streaming.py` holds every streaming scanner against its
  whole-text reference across forced chunk boundaries that land inside
  multibyte characters, escaped quotes and carriage returns, and asserts
  byte-identical reports between disk and memory for every fixture and a
  multi-chunk synthetic filing.
- The three registered-but-unevaluated rules (QP005, QP018, QP032) now carry
  their promotion condition in the reason text every report already prints:
  the exact published evidence that would turn each into an implemented rule,
  and why nothing less would do. No rule changed what it evaluates.
- Correspondence with the Commission's Consumption Data Analytics Unit,
  2026-08-17 to 2026-08-26, answered the three questions this project had
  open, and moved nothing the tool reports. Staff confirmed that the "Valid
  NAICS codes" list is not posted publicly and is not planned to be, that the
  data dictionary holding it is an internal deliverable that will not be
  shared, that the portal rejects a zero padded County Number such as `07`,
  and that Customer Type `O` is accepted for Pacific Gas and Electric. QP018
  stays unevaluated, and its reason now reports its promotion condition as
  declined at the source rather than pending, which is a different state for a
  reader to see. QP024 stays a warning and QP025 stays informational: the
  answers are authoritative and they are private, and a citation in this
  project names something a reader can open. QP024's shortfall against the
  portal is now known and written down instead of merely unconfirmed. ADR 0009
  records what was settled and what was deliberately not moved. The exchange
  is listed in the README's sources and in the source manifest, marked not
  citable, with no url, hash or retrieval date because it is not retrievable.
- The manifest entry for the county table on the Energy Consumption Data Files
  page now names a hash change waiting to happen: its two defective 2024 rows,
  reported to the Commission and confirmed as a data transformation error, are
  corrected but not yet posted. When that hash stops matching, the correction
  is the first thing to check.
- The README described its registered-but-unevaluated rules as "these three"
  while listing four. QP034 joined the table and the sentence did not follow.
- Every document in `docs/source-manifest.md` was re-downloaded on 2026-08-26,
  the pre-release step `CONTRIBUTING.md` describes, and all thirteen hashes
  still match. Only the retrieval dates moved. Notably the county table has
  not changed, so the correction the Commission confirmed on 2026-08-26 is
  not yet posted, exactly as staff said.

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

[Unreleased]: https://github.com/ChelseaKR/qfer-preflight/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ChelseaKR/qfer-preflight/releases/tag/v0.2.0
[0.1.0]: https://github.com/ChelseaKR/qfer-preflight/releases/tag/v0.1.0
