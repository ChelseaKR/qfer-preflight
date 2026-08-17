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

## Rule identifiers are permanent

An identifier is never renumbered and never reused for a different check.
Reports produced by older versions must stay readable. Retiring a rule keeps
its identifier and marks it retired.

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

There is exactly one manual setup step, and it has to be done once before the
first release:

- Set the repository secret **`RELEASE_ALLOWED_SIGNERS`** to the allowed-signers
  line for the SSH key that signs release tags, in the format git's
  `gpg.ssh.allowedSignersFile` expects, for example:

  ```
  you@example.com namespaces="git" ssh-ed25519 AAAAC3Nza...
  ```

Until that secret is set, the verification job stops on its first line and
nothing is published. That is deliberate: without an allowed-signers file
`git verify-tag` has no key to check a signature against, so continuing would
mean releasing a tag nobody verified. `tests/test_release_workflow.py` runs
that guard in a real shell with the secret unset and with it blank, and
asserts both stop the job.

Then, to release, sign an annotated tag on `main`, push it, and run the
workflow with that tag name. The workflow refuses lightweight tags, refuses
tags that are not reachable from `main`, and refuses tags whose signature does
not verify against the allowed-signers line.

## Changing the fail-closed contract

Do not weaken it without an ADR. Specifically: never make a rule report as
passed when it did not run, and never let a structurally broken document
produce the same report as a clean one. `tests/test_fail_closed.py` guards
this and should be treated as load-bearing.
