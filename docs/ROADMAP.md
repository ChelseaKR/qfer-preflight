# Expansion roadmap

This file records where the project could go next and, just as importantly,
what would have to be true before it went there. It is aspirational, not a
commitment, and it is subordinate to `CLAUDE.md`. Nothing below authorises
inventing a specification, a field, a code set or a rule citation. An idea in
this file becomes work only when the published record supports it.

Rule identifiers are permanent. Everything below respects that: new checks get
the next unused `QP` number, retired checks keep theirs forever, and nothing
here renumbers or reuses an identifier.

## Where the project stands

After 0.1.0:

- Five form profiles, their headers transcribed byte for byte from the
  published CSV templates, defects included.
- Twenty-three implemented rules and three registered as permanently
  unevaluated so far (QP005, QP018, QP032), each unevaluated rule carrying a
  stated reason visible in every report.
- Five advisory codes in a closed code space (`ADVISORY_CODES`).
- Three citable source classes: the instruction PDFs, the published CSV
  templates, and the June 24, 2025 DSP workshop deck.
- A fail-closed engine whose contract is hashed into `tests/test_fail_closed.py`,
  an adversarial corpus of twenty six hostile files, and a closed advisory
  channel attacked by `tests/test_advisory_channel.py`.
- Zero runtime dependencies. The validator runs on the standard library alone.
- One gate, `make verify`: format, lint, type check, bandit, tests with a 90
  percent coverage floor, and the dash check.
- Nine ADRs recording the decisions that constrain everything else.

## How anything gets into this project

Every item below must pass the same filter, regardless of which phase it sits
in:

1. Offline only. No network call at runtime, ever. Dev-time tooling that
   fetches nothing at validation time is acceptable; a runtime path that could
   reach the network is a defect.
2. Citation first. A new rule starts as a transcribed quote plus its locator,
   not as an idea looking for a quote. If no published text states the check,
   the outcome is a registered-unimplemented rule with that stated, or a
   documented finding of nothing.
3. Disagreement between published documents is reported as a warning or an
   informational note, never resolved by picking a side (ADR 0003).
4. Applicability is derived from transcribed text, not from lists of profile
   ids (ADR 0007).
5. Anything the reader notices that no published rule covers goes to the
   advisory channel, which means registering the code in `ADVISORY_CODES`
   first, adding a corpus case, and writing an ADR (ADR 0004).
6. Fail-closed is non-negotiable. New capabilities are designed so that a
   document they cannot fully evaluate still cannot report as `pass`
   (ADR 0001).
7. Every landing passes `make verify`, gets a CHANGELOG entry under
   `[Unreleased]`, and gets an ADR if a decision was made. No em dashes or en
   dashes anywhere.

---

## Phase 1: Ground truth hardening

The registry is strong on the checks it makes and silent on the space between
checks. This phase maps that space honestly. Nothing here changes a verdict;
all of it changes what a reader can trust about the map.

### 1.1 Column coverage audit

Produce a maintained matrix, checked into `docs/`, of every column in every
published template against the rules that touch it:

- Which rules cover this column, by identifier.
- Which columns are covered only by the structural rules (QP003 field count,
  QP019 and QP020 numeric hygiene) rather than a field-specific rule.
- Which columns carry **no** published constraint this project can find, with
  the search recorded rather than left implicit. "None found" must look
  different from "not looked at".

The immediate open cells are visible today: `RateClass` on `CEC-1306A-S1`,
`RetailRatClass` and `Description` on `CEC-1306A-S2`, and the amount columns'
semantics beyond numeric hygiene. For each, the deliverable is one of three
outcomes, all legitimate: a new rule with a quote (Phase 3), a new
registered-unimplemented rule stating why, or a recorded finding that the
instructions publish no mechanical constraint for it.

Definition of done: the matrix covers all five headers cell by cell, the README
links to it, and a test asserts every profile header appears in it so a new
column cannot silently skip the audit.

### 1.2 Source manifest

Record, next to the URLs in `profiles.py`, a retrieval date and a SHA-256 for
each cited document: the four instruction PDFs, the five CSV templates, the
workshop deck, and the two Energy Consumption Data Files spreadsheets already
described in the README. A test asserts that every URL the profiles cite
appears in the manifest.

This turns the README's warning, "published documents change, and when they do
this tool is wrong until it is updated", from an act of faith into a
procedure: re-download, compare hashes, and a silent revision announces itself.
It also gives the changelog a concrete way to say which revision of a source a
release was checked against.

Dev-time only. Nothing in the runtime path reads the manifest or touches a
network.

Definition of done: manifest committed, test enforcing completeness, and a
short procedure in `CONTRIBUTING.md` for the re-download ritual.

### 1.3 Written promotion criteria for the unevaluated rules

QP005, QP018 and QP032 are the honest half of the tool. Each should carry, in
one place, the exact evidence that would promote it, so the conditions are
known before the evidence arrives:

- QP018: a transcription job, not a research one, the moment someone supplies
  the portal data dictionary the workshop deck says exists (slide 44 promises
  it). The criteria should say what provenance such a transcription needs
  before it may enter `codes.py`.
- QP005: implemented only if the Commission publishes a marker that
  distinguishes a totals row from a data row. Any heuristic is an invention.
- QP032: implemented only if a published document names the columns forming a
  row's unique reporting key, or publishes that duplicates are legitimate,
  which the Commission's own worked example currently implies.

Definition of done: the criteria live with the rules (extending
`unimplemented_reason` or a section in the coverage document), and the README
points at them.

## Phase 2: Filer-facing capability

These items add convenience without touching rule truth. Each is designed
against the fail-closed contract explicitly.

### 2.1 Profile detection

`check` requires `--profile` today, and a filer with five forms in a folder has
to know which is which. Add optional detection: match the file's header row
against the five transcribed headers. Exactly one match runs it; zero or more
than one match is a usage error listing the near misses, never a guess. The
detection keys are the published headers themselves, so this invents nothing.

Definition of done: detection behind a flag or a default-off path, ambiguity
fails closed, adversarial cases (header off by one character, header matching
two profiles after normalisation attempts) assert refusal.

### 2.2 Batch mode

Validate a directory or a file list in one run: one report per input, an
aggregate summary line per input, and `--format json` gaining a multi-report
envelope. Findings never merge across files. Exit codes need a defined
aggregate rule (proposed: nonzero if any input exits nonzero; usage errors stay
distinct).

Definition of done: mixed directories (valid, failing, unparseable, unknown
profile) produce per-file reports whose statuses match single-file runs
byte for byte, asserted by test.

### 2.3 A published schema for the JSON report

The JSON report is a de facto interface. Publish a JSON Schema document for
it, add an explicit schema version field, and state the compatibility policy:
additive fields are minor, changing or removing existing fields is breaking and
requires a major version. Generate the schema from the model or validate the
model against it in CI, so they cannot drift.

This unlocks the rest of the roadmap's machine-facing items (batch envelopes,
SARIF) on top of something stable instead of something incidental.

Definition of done: schema committed, CI validates real reports against it,
compatibility policy written next to it, changelog records the new field.

### 2.4 Bounded memory for very large filings

`validate_path` reads the whole file once (`engine.py` writes `handle.read()`)
and streams rows after decoding, so peak memory is roughly the file size. For a
filing measured in hundreds of megabytes that is wasteful. Stream the read:
hash incrementally (SHA-256 chains), decode in chunks, feed the CSV reader from
the stream, keeping the existing behaviours that depend on seeing the whole
byte picture (BOM detection, line-ending scan) intact.

The risk is behavioural regression in exactly the paths the adversarial corpus
guards, so this lands only with the corpus extended to prove the advisory
survivals from the 0.1.0 changelog still hold.

Add a benchmark harness, outside the gate: generate a synthetic large fixture
from the published template shape, record wall time and peak memory per
release. Benchmarks inform, they do not gate.

Definition of done: identical reports on a fixture set before and after,
adversarial corpus green, benchmark script committed, memory bounded by a
constant rather than the file size.

### 2.5 SARIF output (optional)

Emit SARIF so the tool can drop into CI surfaces that speak it: findings as
results with severity mapped, advisories as notifications preserving their
no-severity nature, citations in the result message. Purely another serialiser;
still offline, still standard library.

Do this only after 2.3 stabilises the native JSON, and keep SARIF strictly
derived from it rather than becoming a second source of truth.

## Phase 3: Registry growth under the citation bar

Phase 1.1 produces the candidate list; this phase is the method for acting on
it. The order is fixed: read, quote, then decide.

Per candidate:

1. Locate the field definition or sentence in the correct instruction PDF.
   Record the locator precisely enough that another person finds the same
   passage.
2. Transcribe the quote verbatim, defects included, per the transcription
   convention and ADR 0002.
3. Decide the outcome class:
   - Mechanically checkable: a new `RuleSpec`, next unused `QP` identifier,
     with `cites=` pointing at instructions, template or workshop, applicability
     derived from the quote where the text is form-specific, tests including
     hostile inputs, changelog entry.
   - Published but not mechanically checkable: register it unevaluated with a
     reason in the style of QP005 and QP018.
   - Not published at all: the finding of nothing goes in the coverage
     document, and if the reader noticed something real anyway, the advisory
     channel is the only door, with its registration ceremony.
4. If the new text contradicts text another document publishes, stop and apply
   ADR 0003: warning or informational, both sources named, no error.

Specific reading list, none of it verified yet, all of it reachable in
documents already cited:

- `RateClass` on Schedule 1, `RetailRatClass` and `Description` on Schedule 2:
  does either instruction define a value set, a format, or a length?
- The remaining numbered formatting rules on slide 19 of the workshop deck.
  QP024 came from rule 6; rules 1 through 5 and whatever follows have not been
  mined. Remember the deck is used to withhold errors, never to add them
  (ADR 0003), except where the deck is the only source and the instruction
  PDFs are silent, which is exactly the QP025 pattern.
- `CompanyNumber`: described as assigned by CEC staff; confirm whether any
  published text constrains its written form beyond presence (QP021).
- The amount columns: whether any document states units, rounding or sign
  conventions that a mechanical check could honour.

## Phase 4: New form coverage

Coverage expands only when the Commission publishes what a profile needs: a
CSV template to transcribe and instructions that describe its fields. The
triggers and the intake checklist matter more than the dates.

Standing triggers to watch, using the Phase 1.2 manifest ritual:

- `CEC-1306A` Schedule 3 and `CEC-1308B` Schedule 2: both go by SFTP and their
  templates are available only on request. If either template is published at
  a retrievable URL, the intake checklist runs.
- `CEC-1304`: filed by email or mail, form is a spreadsheet, no CSV template.
  Out of scope unless the Commission publishes a CSV channel. Approximating a
  spreadsheet form remains rejected.
- Any revision of the four current instruction PDFs (rev. 07/14/2025) or the
  five templates. Hash drift is the signal; a revision can invalidate quotes,
  severities and even the QP007 applicability split, which is derived from
  transcribed text and therefore follows the text automatically (ADR 0007).
- The data dictionary the workshop deck promises. If it is published openly,
  QP018 becomes a transcription job, the Customer Type `O` question may gain
  the text ADR 0005 says would flip it, and the customer group and rate code
  sets gain corroboration or contradiction worth an ADR either way.

Intake checklist per new profile, each step leaving an artefact:

1. Transcribe the header byte for byte, irregularities included, with the
   template URL and retrieval date recorded (ADR 0002).
2. Record the authority the form cites.
3. Walk every field definition in the instructions; assign column roles; run
   the Phase 1.1 audit for the new header.
4. Allocate the next unused `QP` identifiers; never renumber anything.
5. Extend profile detection (2.1) and batch fixtures (2.2).
6. Build the adversarial fixtures for the new header shape.
7. Write the ADRs any disagreements demand, before the code.

## Phase 5: Quality and supply chain

- Adversarial corpus growth. Twenty six cases exist. Target: every new engine
  capability in Phases 2 and 3 lands with at least one hostile input that
  tries to make it silent, and the corpus gains a documented category per new
  advisory ever added. The central assertion stays one line: no hostile input
  produces a report with neither findings nor advisories nor errors.
- Property-based testing. Hypothesis in the dev dependency group only (the
  runtime stays empty), generating CSVs that violate one invariant at a time
  and asserting the verdict moves away from `pass`. Start with digit classes,
  the failure that motivated the `[0-9]` convention.
- Coverage floor path. Ninety percent today; raise toward 95 once Phases 1 and
  2 settle, rather than letting new code arrive under a floor it immediately
  erodes.
- Mutation testing study. Run mutmat-style tooling offline as a non-gating
  experiment to locate tests that assert nothing, especially around merging
  and the advisory channel, where a vacuous test would hide the most.
- Platform matrix. The package is pure Python, but encoding and line-ending
  behaviour deserves evidence on Windows as well as macOS and Linux. Add one
  CI job running the suite end to end.
- Python support. 3.12 and 3.13 declared today; add 3.14 when the toolchain
  (ruff, mypy, uv) supports it, and keep `requires-python` honest.
- Release hardening continues along the lines already in place: tag and
  version agreement, signed artifacts with `allowed_signers`, `make verify`
  re-run at the tagged commit. Consider generating an SBOM from the lockfile
  at release time, which costs little given the empty runtime dependency set.

## Phase 6: Documentation and stewardship

- A filer guide: one short page per profile with a synthetic worked example
  built from the published template, what each exit code means, when `--strict`
  is the right setting, and what an unevaluated rule means for the filing
  decision. Examples are labelled synthetic; none imply any real submission.
- A glossary for terms the sources use: QFER, DSP, UDC, LSE, TEOR, UEG,
  NAICS, and the distinction between a rule, an advisory and an unevaluated
  rule.
- `CONTRIBUTING.md` gains two recipes: how to propose a rule (quote, URL,
  locator, proposed identifier; proposals without quotes are declined), and
  how to report a value some published CEC document calls valid that the tool
  rejects. The second is the highest-value defect class this project can
  receive, since it strikes directly at ADR 0003 and ADR 0005 territory.
- A source-watch rhythm tied to the filing calendar the instructions publish
  (data due by the 15th of February, May, August and November): re-download
  the manifest documents shortly before each, compare hashes, and treat any
  drift as a priority fix with a changelog entry saying which revision changed.
- Keep writing ADRs at the same density. The nine that exist are why the
  guardrails are load-bearing rather than decorative. Anything in this roadmap
  that changes an output contract, a channel, or a severity decision gets the
  next number.

## Explicitly out of scope, restated

Ideas that recur and stay rejected, with the reason attached so they are not
relitigated from scratch:

- Runtime network features: checking whether a cited URL is still live,
  fetching revised templates, update pings. The tool reads local bytes; the
  manifest ritual covers currency at dev time.
- Heuristics for totals rows (QP005) or duplicate keys (QP032). Both would
  guess where the Commission's own examples contradict the guess.
- Substituting the federal Census NAICS list for QP018. No CEC text equates
  the two, and the RE custom codes prove the sets differ.
- Auto-fixing filings. Editing a filing crosses from describing published
  text to judging it; the tool stops at description.
- GUI or web surface. Accessibility and i18n rows in the standards table stay
  N/A because there is deliberately no UI to bind them to.
- Telemetry of any kind, including opt-in crash reporting. The run report is
  the entire output surface.
- Approximations of `CEC-1304` or the SFTP schedules. A validator built on
  almost-transcriptions is worse than none, because it borrows the credibility
  of the ones that were transcribed exactly.

Any of these flips only when the published record changes, and each flip
starts with a quote.

## Sequencing

Indicative order, each phase mostly independent of the later ones:

| Order | Work | Depends on | Definition of done |
|-------|------|------------|--------------------|
| 1 | Column coverage audit (1.1) | nothing | matrix complete, test-enforced, README linked |
| 2 | Source manifest (1.2) | nothing | hashes committed, completeness test, ritual documented |
| 3 | Promotion criteria (1.3) | 1.1 preferred | criteria live with QP005, QP018, QP032 |
| 4 | Report schema (2.3) | nothing | schema validated in CI, policy written |
| 5 | Profile detection (2.1) | 1.2 helpful | ambiguity fails closed, corpus extended |
| 6 | Batch mode (2.2) | 2.3 for envelope | parity with single-file runs asserted |
| 7 | Registry growth (3) | 1.1 | each candidate ends in one of three recorded outcomes |
| 8 | Bounded memory (2.4) | corpus extensions | identical reports, constant memory |
| 9 | SARIF (2.5) | 2.3 | derived from native JSON only |
| 10 | Quality and stewardship (5, 6) | continuous | ongoing, tracked here |

Phases 1 and 2 items are safe to run in any order among themselves. Phase 3
should wait for 1.1 so the reading effort lands where the map says the gaps
are. Phase 4 waits for events, not for code.
