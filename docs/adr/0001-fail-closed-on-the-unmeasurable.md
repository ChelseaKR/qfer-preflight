# 0001. Fail closed on the unmeasurable

- Status: Accepted
- Date: 2026-08-17

## Context

A validator's most dangerous failure is a false clean. If a submission cannot
be parsed, or its header does not match the template, a naive implementation
runs zero row checks, collects zero findings, and prints a reassuring
"0 errors". The filer reasonably reads that as approval. The tool has in fact
validated nothing.

The same hazard applies to published rules that cannot be tested
mechanically. The CEC instructions prohibit totals rows but publish no marker
distinguishing one from a data row. They require NAICS codes to match a list
of "Valid NAICS codes" that is not published at any retrievable URL. Silently
omitting these rules would let a submission that violates them come back
looking clean.

## Decision

Three commitments.

1. **Structural failure blocks downstream rules.** Unreadable input leaves
   every other rule unevaluated. A header mismatch leaves every
   column-dependent rule unevaluated, because without a correct header the
   engine cannot map columns to fields.

2. **Unimplementable rules are registered, not omitted.** A published rule
   with no deterministic test is registered with `implemented=False` and a
   stated reason, and appears in the unevaluated list of every report.

3. **`pass` requires total coverage.** The verdict is `pass` only when there
   are no errors *and* every applicable rule was evaluated. Otherwise it is
   `unvalidated`. Since every profile registers at least one unimplementable
   rule, a spotless file reports `unvalidated`. That is the intended result.

`tests/test_fail_closed.py` hashes the reports for a clean file, an empty file
and a malformed file, and asserts all three digests differ.

## Consequences

The tool never says "clean", which some users will find unsatisfying. That
discomfort is the honest signal: it reflects a real limit in what the
published specifications allow anyone to check. `--strict` lets a caller treat
any unevaluated rule as a failure. The alternative, a green check mark over an
unexamined file, would make the tool worse than useless.
