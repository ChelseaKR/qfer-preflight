# Improvement plan: gates that cannot fail

Written after an audit whose one question was the one this repository already
answers about its own output: can this check report the thing it exists to
report? A check that cannot fail is worse than no check, because it also
spends the credibility of the ones that can.

The audit followed the `no-dashes` repair of 2026-08-27. That target searched
for `\xe2\x80\x93`, which in a PCRE is the codepoint U+00E2 rather than a
UTF-8 lead byte, so it matched nothing and printed success on every run. The
assumption here was that it would not be the only one.

## Method

Every claim below was established by breaking the thing and watching what
happened, not by reading the code and reasoning about it.

- **Rule census by AST.** `rules.py` was parsed for every `RuleSpec`, and the
  whole package for every `collector.add(...)` and `collector.advise(...)`
  emission site, including the two indirect paths where the rule id arrives as
  a parameter (`_check_enum_cell`, `_check_integer_range`) and the one where
  it arrives from a tuple table (`enum_checks`). A regex over `[A-Z_]+` would
  have missed every id in this repository, because they all contain digits.
- **Falsifiability by mutation.** Each rule and advisory was suppressed in
  turn and the suite re-run, to find any rule the source emits that no test
  proves fires. Then each was forced to fire spuriously on every data row, to
  find any rule whose *silence* on clean input nothing pins.
- **Guard mutation.** Each invariant the code defends was broken at its
  source, the suite re-run, and the file restored. A guard whose removal
  leaves the suite green is a guard nothing is holding.

## Findings

### Clean: the rule registry is falsifiable in both directions

All 24 implemented rules and all 5 advisory codes were suppressed one at a
time. Every one turned the suite red. All 29 were then forced to fire
spuriously. Every one turned the suite red again. There is no registered rule
here that no test proves fires, and no rule whose clean case is unpinned.

The AST census also found no orphans in either direction: every implemented
rule has exactly one emission site, every unimplemented rule has none, no
emission site names an unregistered rule, and no advisory code is registered
without being reachable.

### Defect 1: a report can list the same rule as evaluated and not evaluated

`model.py` states the invariant outright: "Every rule applicable to a profile
ends up in exactly one of `rules_evaluated` or `rules_not_evaluated`."
Two independent lines defend it, `self._evaluated.discard(rule_id)` in
`mark_not_evaluated` and `- set(self._not_evaluated)` in the `evaluated`
property. Removing **both** leaves the suite entirely green.

With both removed, `wrong_header.csv` produces a report listing QP003 in both
lists at once: a report claiming it applied a check it also says it never
applied. `_refuse_contradictions` does not catch it, because it only checks
the opposite direction, a finding citing a rule absent from `rules_evaluated`.

The invariant holds today on every path tried. It is not enforced and not
tested, so the next change to the gating can break it in silence.

### Defect 2: `_refuse_contradictions` has no test proving it fires

Making the whole function `return` immediately leaves the suite green. Its
raise carries `# pragma: no cover`, so the coverage floor does not see it
either. It is a guard nothing is holding.

### Defect 3: the `[0-9]` convention is unenforced, and one regex is unguarded

`CLAUDE.md` requires digit classes to be written `[0-9]` and never `\d`,
because `\d` matches every Unicode decimal digit and `int()` converts them,
which once let a fullwidth Month through with no finding at all.

Four regexes in `engine.py` follow the convention. Changing three of them to
`\d` turns the suite red. Changing the fourth,
`_COMPANY_NUMBER_DIGITS`, leaves it **green**: QP033 would accept a Company
Number written in fullwidth or Arabic-Indic digits and report nothing. The
adversarial corpus covers Year, Month and the numeric columns; Company Number
was added later, by QP033, and no case followed it.

Nothing in the repository enforces the convention at source level, so the
same regression can be reintroduced in any new regex.

### Defect 4: `make no-dashes` fails open on any git error

The repaired target is

```make
@if git grep -n -P '\x{2013}|\x{2014}' -- ':!*.lock' ':!uv.lock' > /tmp/qfer-dashes.txt 2>/dev/null; then \
  echo "Found em/en dashes in tracked files:"; cat /tmp/qfer-dashes.txt; exit 1; \
else \
  echo "no em/en dashes"; \
fi
```

`git grep` exits 0 when it matches, 1 when it does not, and 128 when it fails.
The `else` branch takes 1 and 128 alike, and `2>/dev/null` throws away the
message that would have said which. A malformed pattern, exactly the class of
defect that made this gate dead for the repository's whole life, makes it
announce "no em/en dashes" and exit 0. Verified: `git grep -P 'bad['` exits
128 and the target reports success.

The gate was repaired so it can fail on a dash. It still cannot fail on being
broken.

It also writes to a fixed path in the shared temp directory, which collides
between concurrent runs and between users on one machine.

### Defect 5: mypy does not look at `scripts/`

`pyproject.toml` sets `files = ["src", "tests"]`. `scripts/` is linted by ruff
and type-checked by nothing. Verified by appending

```python
def audit_probe(x: int) -> str:
    return x
```

to `scripts/bench_large_file.py`: `make typecheck` reports "Success: no issues
found in 27 source files" and `make verify` stays green.

### Defect 6: the secret scan does not scan what its name says

`.github/workflows/security.yml` runs a step named **"Scan the working tree
and history"**:

```sh
./gitleaks detect --source . --redact --no-banner --exit-code 1
```

In gitleaks 8.30.1 `detect` scans git history; `--no-git` is what scans the
files on disk. Verified in a scratch repository with a private key block, a
pattern gitleaks does not allowlist: with the secret present in the working
tree and absent from history, `detect` exits 0 and `detect --no-git` exits 1.

Tracked files in a CI checkout did arrive through some commit, so the history
scan covers them in practice. The step name still asserts a scan that is not
performed, and anything generated into the workspace is outside it.

### Defect 7: CI and the Makefile can drift apart

`make audit` exists and no workflow invokes it; `security.yml` inlines the
same four commands instead. The secret scan has no make target at all. So
`make verify` can be green on a tree CI rejects, and `make audit` can rot
without any run noticing. Nothing tests that the two agree.

## Phases

Each phase lands with a test that fails before the change and passes after,
and each guard added or repaired is broken deliberately, watched to fail,
restored, and watched to pass.

1. **Enforce the partition.** Extend `_refuse_contradictions` to refuse a rule
   in both lists, and to refuse an applicable rule in neither. Test both
   directions directly, so the guard itself is falsifiable. Closes 1 and 2.
2. **Close the Company Number digit gap.** Add adversarial cases for a
   Company Number written in Unicode digits, asserting QP033 fires. Closes the
   live half of 3.
3. **Enforce the `[0-9]` convention at source.** A `make no-unicode-digits`
   target and a test built the way `test_dash_gate.py` is built: assert the
   pattern against a real `\d` occurrence rather than trusting it by eye.
   Closes the systemic half of 3.
4. **Make the text gates fail closed.** Teach `no-dashes` to tell exit 1 from
   exit 128 and fail on the latter, and stop using a fixed temp path. Closes 4.
5. **Widen the type check.** Add `scripts` to mypy's files and fix what falls
   out. Closes 5.
6. **Make the workflows say what they do.** Add the working-tree pass to the
   secret scan, give it and the audit make targets, have `security.yml` call
   them, and test that every gate CI runs exists as a make target. Closes 6
   and 7.

## Out of scope, and why

- **QP018, the "Valid NAICS codes" list.** Not implementable. The list is not
  published at any URL this project can retrieve, and the Commission answered
  on 2026-08-26 that it will not be. Substituting the Census Bureau list would
  be an invention, since the Commission's accepted set includes per-utility
  custom codes. Left registered and unevaluated, as ADR 0009 records.
- **QP005 totals rows, QP032 duplicate keys, QP034 commas.** Each is
  registered with a stated reason and a promotion condition naming the
  published text that would settle it. No such text was found during this
  audit, and none was invented. They stay unevaluated.
- **Issue #14, SARIF `ruleIndex`.** Already fixed by PR #21; `ruleIndex` is
  built as `len(rules)` before each append. The issue is stale, not open work.

## Phase 7: four assertions that could not be false

Found by a second pass over the test files that check the project's own
documents and outputs, rather than its validation logic.

- **`test_source_manifest.py`** asserted `assert date(year, month, day), "..."`.
  `datetime.date` defines no `__bool__`, so every date object is truthy: the
  assertion could never be False and its message was unreachable. What caught a
  bad date was the `ValueError` inside `date(...)`, reported by pytest as an
  error rather than a failure and carrying a stdlib message. The construction is
  now the check, deliberately and with the authored message.
- **`test_source_manifest.py`** compared `len(urls) == len(hashes) == len(dates)`
  file-wide. An entry carrying two hashes beside a neighbour carrying none
  satisfies it, which was verified by planting exactly that: the totals stayed
  13/13/13 and the test stayed green. Each entry is now checked for its own
  triple, because the manifest can only announce a revision for a document whose
  hash sits next to its own url.
- **`test_batch.py`** asserted `code in (EXIT_OK, EXIT_FINDINGS, EXIT_USAGE)`,
  which is every value `main` can return. Four tests routed through that helper
  with no exit-code coverage at all. Demonstrated by making a clean batch return
  `EXIT_USAGE`: with the repaired assertion one test fails, with the original
  all eleven pass.
- **`test_sarif.py`** asserted `isinstance(index, int)` on advisory results while
  its sibling for rule results wrote `isinstance(index, int) and not
  isinstance(index, bool)`. `bool` subclasses `int`, so `ruleIndex: true` passed
  the weaker one and `rules[True]` resolves silently to `rules[1]`: the wrong
  rule, resolved without complaint. The two now agree.

`test_batch.py::test_batch_entry_requires_exactly_one_of_report_or_problem`
also tested neither and each one alone, never both, so the "exactly one" half of
its name was unasserted. It is now.
