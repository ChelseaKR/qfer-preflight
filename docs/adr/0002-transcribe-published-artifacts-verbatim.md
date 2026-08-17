# 0002. Transcribe published artifacts verbatim, including their defects

- Status: Accepted
- Date: 2026-08-17

## Context

The published CSV templates contain irregularities. The `CEC-1306A` Schedule 1
header spells its seventh column `NumberofCustomers` with a lower case "o",
while every sibling template writes `NumberOfCustomers`. The Schedule 2 header
spells its fourth column `RetailRatClass`, which reads as a typo for
`RetailRateClass`. The instruction PDFs have their own small inconsistencies,
including one footnote reading "letter" where its siblings read "letters".

There is a standing temptation to normalise these.

## Decision

Transcribe published artifacts exactly, defects included.

Header tuples in `profiles.py` match the published template bytes. Rule quotes
in `rules.py` match the published wording, per document, with the sole
normalisation that typographic quotation marks are written as ASCII. Where
sibling documents word the same requirement differently, the quote is keyed by
profile so each rule cites what its own document actually says.

Code set tables are transcribed with no gap filling. The published residential
code table has no `RE3100`, `RE3500`, `RE3600` or `RE3800`, so neither does
the transcription, and a test asserts their absence.

## Consequences

The code carries oddities that look like bugs and need comments explaining
that they are faithful. Accepted, because the tool's job is to predict what
the portal will accept, not what a tidier template would have specified. If
the CEC corrects a template, that is a rule change with a CHANGELOG entry, not
a silent fix.
