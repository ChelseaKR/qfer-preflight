# 0003. Never assert an error that a published source contradicts

- Status: Accepted
- Date: 2026-08-17

## Context

ADR 0001 covers the case where nothing is published: the rule is registered
and reported as unevaluated. It does not cover the case where two published
Commission documents say different things about the same value.

That case is real. Reading the slide deck from the Commission's June 24, 2025
Data Submission Portal workshop against the instruction PDFs revised on
July 14, 2025 turned up two disagreements.

**Customer Type.** The CEC-1306A instructions list three values: "D = Direct
Access Customer, B = Bundled Customer, C = Community Choice Aggregation." The
workshop deck, slide 9, lists four: "Valid values for Customer Type (uppercase
letter): B (Bundled), D (Direct Access), C (Community Choice Aggregator),
O (for BART, PGE only)". Before this was found, the tool reported `O` as an
error, which would have been a false alarm for the one filer entitled to use
it.

**Zero-padded County Number.** The published county table writes counties 1 to
58 unpadded and writes only Unknown as "00", and the instructions give the type
rule as "numeric data type for county numbers 1-58 and 99, and text data type
for county "00"". But the workshop deck, slide 19, formatting rule 6, reads:
"Any Company Number, County Number, and NAICS code values that contain a
leading 0 (zero) should be formatted as TEXT data type." That sentence tells a
filer how to preserve a leading zero on a County Number. It does not call the
value wrong. Meanwhile every published example writes county numbers unpadded,
and the Commission's own published error example for the field is a negative
number, "County Number: -24", not a padded one. Before this was found, the tool
reported `07` as an error on no published authority at all.

Both had the same shape: the tool was asserting a violation that a published
document contradicts.

## Decision

**A finding may only be reported at error severity when no published source
contradicts it.** When published sources disagree about a value, the tool
reports the disagreement instead of picking a side.

Concretely:

1. The value does not produce an error. Reporting one would be claiming that
   the published rules say something they do not agree on.
2. The disagreement is surfaced as its own rule with its own permanent
   identifier, at warning or informational severity, citing the document that
   permits the value. The filer learns that the sources differ and can ask the
   Commission.
3. The rule that would otherwise have fired keeps its own citation and its own
   behaviour for every other value. QP014 still fails `X`. QP013 still fails
   `77`, `-24` and `007`.

This produced QP024, a warning that a County Number is zero padded, and QP025,
an informational note that Customer Type `O` appears in the workshop deck and
not in the instructions.

The cover extends only as far as the published text does. Formatting rule 6
speaks of a value that "contains a leading 0", which for a County Number can
only mean the two-character forms `01` through `09`, since `00` is already in
the table. `007` has no published cover and remains an error.

## Consequences

The tool is quieter than a maximally strict reading of the instructions alone
would make it, and a filer who submits `O` or `07` may still be rejected by the
portal. That is the correct trade. This tool exists so a filer can trust that
what it flags is genuinely published as wrong; a validator that cries wolf on a
value the Commission itself documents as valid teaches filers to ignore it, and
an ignored validator catches nothing.

Note the asymmetry with ADR 0001. Silence in the published record means the
tool declines to reach a verdict and says so loudly. Conflict in the published
record means the tool declines to condemn, and says that loudly too. Neither
resolves into a quiet pass.

The DSP workshop deck is now a cited source alongside the instruction PDFs and
the CSV templates. It is a slide deck, which is a weaker artifact than an
instruction document, and it predates the current instructions by three weeks.
It is used only to withhold an error, never to add one.
