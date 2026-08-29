# 0010. The six unallocated rule identifiers

- Status: Accepted
- Date: 2026-08-29

## Context

The registry runs from QP001 to QP034 with six identifiers absent: QP008,
QP009, QP026, QP027, QP028 and QP029. Nothing anywhere said why.

That sits badly beside this project's standing promise that an identifier is
never renumbered and never reused. A reader who noticed the gap could not tell
whether those six rules were withdrawn, written and lost, or never written at
all, and the three readings mean very different things. The worst of them,
that a check once existed and its finding no longer appears, is the one a
filer would care about most.

The question has an answer, and the answer is checkable.

**The six identifiers have never been used.** Every commit, branch, tag and
unreachable object in this repository's history was searched for the six
strings on 2026-08-29. `git log -S` across `--all` returns nothing for each of
them. Reading every blob reachable from every ref, together with the dangling
objects `git fsck` reports, finds none of them either. No rule was withdrawn.
No rule was lost. Nothing was ever numbered QP008, QP009, or QP026 through
QP029.

What the gaps line up with is the shape of the registry. `RULE_SPECS` is
divided into three commented sections, and in the first commit each began on a
round number: structural rules at QP001, field rules at QP010, cross-row rules
at QP030. That first commit ended those sections at QP006, QP023 and QP032, so
each block was laid out with room above its last rule. QP007 later took part of
the first block's headroom, and QP024 and QP025 part of the second's. QP008,
QP009 and QP026 through QP029 are the headroom nothing ever took.

**Why the blocks were spaced that way is not on the record.** No commit
message, ADR, CHANGELOG entry, pull request description or issue in this
project states it. This ADR does not supply a reason it cannot source. The
alignment above is an observation about the file, offered as that and not as a
recovered intention.

The spacing is also not a scheme this project still follows, so a reader should
not infer one from it. QP033 is tagged `field`, and the field block's first
free identifier was QP026, but QP033 is the identifier it was given: the
roadmap's intake checklist says to allocate the next unused identifier, and
that is what happened.

## Decision

- **The six identifiers stay unallocated.** No future rule is numbered into
  them. Nothing forbids it, strictly: they have never been used, and the
  permanence rule bars reuse rather than first use. But a reader who sees QP026
  appear in a report in 2027 has no way to tell a newly written rule from a
  restored one, and this project is not in the business of producing an
  identifier whose meaning depends on which version wrote it. Six numbers are
  cheaper than that ambiguity.
- **New rules take the next unused identifier above the highest allocated
  one**, which is what the roadmap already says and what QP033 and QP034
  already did.
- **The list above is held against the registry by a test.**
  `tests/test_rules.py` derives the unallocated set from `RULE_SPECS` and
  compares it to the six recorded here, and separately checks that this file
  names each one. Allocating one of the six, or opening a new gap without
  amending this ADR, fails the build rather than quietly restoring the state
  this ADR exists to end.

## Consequences

- The question this ADR opens with now has a written answer, and that answer
  separates "never written" from "withdrawn". That is the distinction a reader
  of a report needs, and it is the one the gap alone could not settle.
- The identifier space is sparse and stays sparse. This costs nothing. An
  identifier is a label, not an index, and no code counts on the sequence being
  dense.
- The load-bearing half of this ADR is the half that says the origin of the
  spacing is not recorded. The alternatives were to leave the gap unexplained,
  or to write down a plausible reason nobody can check. This project refuses
  the second of those for a CEC rule, and it refuses it here too. An invented
  explanation of its own history would be the same defect wearing different
  clothes.
