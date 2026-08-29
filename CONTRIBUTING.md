# Contributing

## The rule that outranks the others

**Never invent a specification, a field, a code set, or a rule citation.**

Every rule in this project cites published text. A rule that cites something
nobody published would poison the only thing the tool is good for. If you
cannot find an authoritative published source for a check, you have two honest
options:

1. Register the rule with `implemented=False` and a `unimplemented_reason`, so
   every report lists it as unevaluated.
2. Leave it out, and say so in the README.

There is no third option. A pull request that adds a plausible-sounding rule
without a citation will be declined, however useful the check seems.

## Getting set up

```sh
uv sync
make verify
```

`make verify` runs formatting, linting, type checking, a security scan, the
tests with the coverage floor, and the dash check. It is the same set CI runs.
Run `make verify` before opening a pull request and make sure it exits 0.

```sh
uv run pre-commit install   # optional, runs the fast checks on commit
```

## Adding a rule

1. Find the published source. Read the primary document, not a summary of it.
2. Add a `RuleSpec` to `src/qfer_preflight/rules.py` with:
   - the next unused identifier (never reuse or renumber one),
   - a `Citation` naming the document, its URL and the locator within it,
   - a `quote` transcribed from that document.
3. Wire the check into `src/qfer_preflight/engine.py`.
4. Add tests for both the passing and the failing case.
5. Add a CHANGELOG entry under `[Unreleased]`.

If sibling documents word the same requirement differently, key the quote by
profile rather than picking one wording and applying it to all of them. See
ADR 0002.

## Proposing a rule without writing one

You do not have to open a pull request. A proposal is welcome, and it is
accepted or declined on one thing: whether it comes with the published text.

Include all four of these:

1. **The quote**, transcribed exactly from the document, defects included. Not
   a paraphrase and not a summary of what the document means.
2. **The document**, by name and URL. If it is one of the documents in
   `docs/source-manifest.md`, say so; if it is not, say why it should be
   citable at all.
3. **The locator** inside it: the section heading, the field definition, the
   footnote, the slide number. Precise enough that another person opens the
   document and lands on the same passage.
4. **What the check would do** on a value that violates it, and at what
   severity.

A proposal without a quote is declined, however sensible the check sounds.
That is not a comment on the proposer; it is the rule the project runs on, and
it applies to its own maintainers. If the published text you have in mind
turns out not to exist, that is a real finding too, and it belongs in
`docs/column-coverage.md` as a recorded search rather than nowhere.

If the text exists but cannot be tested mechanically, say so and propose it as
an unevaluated registration in the style of QP005. Those are as valuable as
implemented rules, and they are the honest half of the tool.

## Reporting a value the tool rejects that a published document calls valid

**This is the most valuable defect report this project can receive.** It goes
straight at ADR 0003 and ADR 0005: a validator that flags a value the
Commission itself documents as valid is one that filers learn to ignore, and
an ignored validator catches nothing.

Include:

1. **The value and the column**, and the profile you ran, plus the finding as
   the tool printed it, rule identifier and all.
2. **The published document that says the value is valid**, with URL, locator
   and the quote. The same bar as a rule proposal, for the same reason.
3. Whether the document is the same one the rule cites or a different one.
   That distinction decides the outcome.

The two outcomes differ:

- **Same document, misread by the tool.** That is a plain defect. The rule is
  wrong about what its own source says and gets fixed, with a test.
- **A different published document.** Then two Commission documents disagree,
  and ADR 0003 governs: the error is withdrawn, and the disagreement is
  reported at warning or informational severity, citing the document that
  permits the value, with both sources named. That is how QP024 and QP025
  came to exist. It needs an ADR, not just a patch.

One thing that cannot move a severity, however authoritative it is: an answer
from Commission staff by email, or anything else a reader cannot open. ADR
0009 records a case where all three open questions were answered that way and
nothing changed, and explains why. Send it anyway. It gets recorded as
correspondence, it may close a search, and it will never be cited.

## Rule identifiers are permanent

An identifier is never renumbered and never reused for a different check.
Reports produced by older versions must stay readable. Retiring a rule keeps
its identifier and marks it retired.

New rules take the next unused identifier above the highest allocated one. Do
not number into the six gaps in the sequence, QP008, QP009 and QP026 through
QP029; ADR 0010 records what is known about them, which includes that none of
them has ever been used and that the reason for the spacing is not on the
record. A test in `tests/test_rules.py` holds that list against the registry,
so changing the identifier space fails the build until the ADR is amended.

## Transcription conventions

Published text is copied exactly, defects included. The only normalisation is
that typographic quotation marks become ASCII quotation marks. Do not correct
spelling in a quote, and do not tidy a published column name. See ADR 0002.

Do not use em dashes or en dashes anywhere in this repository. `make verify`
enforces it.

## Releasing

The release workflow is manual (`workflow_dispatch`) and split in two. The job
that checks out repository content can only read; the job that can write never
checks out content. Verification has to succeed before publication starts.

The key that signs release tags is committed at **`.github/allowed_signers`**,
one line per identity, in the format git's `gpg.ssh.allowedSignersFile`
expects, for example:

```
you@example.com namespaces="git" ssh-ed25519 AAAAC3Nza...
```

While that file holds no principal, only comments and blank lines, the
verification job stops on its first line and nothing is published. That is
deliberate: without a populated allowed-signers list `git verify-tag` has no
key to check a signature against, so continuing would mean releasing a tag
nobody verified. `tests/test_release_workflow.py` runs that guard in a real
shell against a missing file, an empty file and a comment-only file, and
asserts all three stop the job.

To release, sign an annotated tag on `main`, push it, and run the workflow
with that tag name. The workflow refuses lightweight tags, refuses tags that
are not reachable from `main`, refuses tags whose signature does not verify
against the committed allowed-signers list, re-runs `make verify` at the exact
tagged commit, and refuses a tag whose name disagrees with the version in
`pyproject.toml`.

## Keeping the source manifest current

`docs/source-manifest.md` records a retrieval date and a SHA-256 for every
published document a citation resolves to. When you touch a citation, or before
a release, re-download the documents and compare hashes. The procedure for a
hash that no longer matches is at the top of that file, and it begins with
"stop": a changed document can invalidate quotes, severities and header
transcriptions, and the drift is a finding to be handled deliberately, not a
line to refresh.

`tests/test_source_manifest.py` refuses a profile-cited document that is absent
from the manifest, so new citations cannot skip it.

## Changing the fail-closed contract

Do not weaken it without an ADR. Specifically: never make a rule report as
passed when it did not run, and never let a structurally broken document
produce the same report as a clean one. `tests/test_fail_closed.py` guards
this and should be treated as load-bearing.
