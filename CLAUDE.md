# Notes for coding agents

## The rule that outranks everything else

**Never invent a specification, a field, a code set, or a rule citation.**

This repository's entire value is that every finding cites published text. A
rule citing a source you fabricated would be worse than no tool at all. If you
cannot find an authoritative published source, either register the rule with
`implemented=False` and a stated reason, or leave it out and note it in the
README. Never guess.

## Scope

- Validates CEC QFER Consumption CSV filings, filer-side, before submission.
- Five profiles: `CEC-1306A-S1`, `CEC-1306A-S2`, `CEC-1306B`, `CEC-1308B-S1`,
  `CEC-1308C`.
- `CEC-1304` is out of scope. Its instructions say reports "can be submitted by
  email or U.S. mail", its form is a spreadsheet, and it has no published CSV
  template. `CEC-1306A` Schedule 3 and `CEC-1308B` Schedule 2 are out for the
  same reason: SFTP channel, templates only on request.
- Three published sources are cited: the instruction PDFs, the CSV templates,
  and the June 24, 2025 DSP workshop deck. A rule picks one with `cites=`.

## Hard guardrails

- Offline only. No network calls at runtime, no telemetry, no accounts, no
  caching of input data. A code path reaching the network is a defect.
- Never claim or imply affiliation with, endorsement by, or approval from the
  California Energy Commission.
- Never write copy implying users, adopters, downloads, or production scale.
- No em dashes or en dashes anywhere. `make verify` enforces it.
- Rule identifiers are permanent. Never renumber or reuse one.
- Never let an unevaluated rule report as passed. See ADR 0001 and
  `tests/test_fail_closed.py`, which is load-bearing.
- Never report an error at a value some published CEC document says is valid.
  When two published documents disagree, report the disagreement at warning or
  informational severity instead of picking a side. See ADR 0003 and ADR 0005.
- Never let a report be silent about something the reader noticed. Anything no
  published rule covers goes in the advisory channel, with an `ADV-` code, no
  severity and no citation, and it keeps the verdict off `pass`. Advisories are
  not a back door for checks that could not survive as rules: an advisory
  cannot carry a severity or a citation, and must say in its own text that no
  published rule covers it. See ADR 0004 and
  `tests/test_adversarial_input.py`, also load-bearing.
- Write digit classes as `[0-9]`, never `\d`. Python's `\d` matches every
  Unicode decimal digit and `int()` converts them, which once let a fullwidth
  Month through with no finding.

## Build entrypoint

```sh
uv sync
make verify
```

`make verify` is the same set CI runs: format check, lint, type check, bandit,
tests with the coverage floor, and the dash check.

## Layout

- `src/qfer_preflight/codes.py` published code sets, each with its provenance
- `src/qfer_preflight/profiles.py` form templates and exact header rows
- `src/qfer_preflight/rules.py` the rule registry with citations and quotes
- `src/qfer_preflight/engine.py` execution and the fail-closed gating
- `src/qfer_preflight/describe.py` rendering values and header rows in words,
  so a message names what the eye cannot see. It decides nothing.
- `src/qfer_preflight/model.py` citation, rule, finding, advisory and report types
- `docs/adr/` decisions, including the fail-closed contract

## Transcription convention

Published artifacts are copied exactly, defects included. Two published header
typos (`NumberofCustomers`, `RetailRatClass`) are reproduced deliberately. Do
not "fix" them. See ADR 0002.
