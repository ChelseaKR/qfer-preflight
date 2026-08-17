# 0007. QP007, a repeated header row, on the two forms whose text covers it

- Status: Accepted
- Date: 2026-08-17

## Context

`ADV-REPEATED-HEADER` fires when a data row is an exact copy of the header
row. It most often means several quarters were pasted into one file. It was an
advisory rather than a rule because, at the time it was written, no published
text appeared to address it, and ADR 0004 sends anything the reader notices
without a citation to the advisory channel.

Re-reading the advisory against its own contract turned up a problem. Every
advisory has to say in its own words that the published record does not cover
what it noticed. This one could not truthfully say that on all five forms.

The "Important Template Notes" sentence differs between the instruction
documents. The CEC-1306B instructions read:

> (2) Exclude any extra information, including extra headers, data for other
> fields, miscellaneous calculations, blank rows, or totals.

CEC-1308C publishes the same sentence. CEC-1306A and CEC-1308B publish it
without the words "extra headers":

> (2) Exclude any extra information, including data for other fields,
> miscellaneous calculations, blank rows, or totals.

Both wordings were already transcribed in `rules.py`, keyed by profile, and
already cited by QP003, QP004 and QP005. So on two of the five forms the tool
was declining to cite text it had in front of it, and an advisory was
asserting an absence in the published record that was not absent.

This is the mirror image of ADR 0003. There the tool was asserting an error a
published document contradicts. Here it was withholding one a published
document supports.

## Decision

**QP007 is registered: a submission must not repeat the header row among its
data.** It is an error, citing the "Important Template Notes" sentence of the
form's own instructions.

**It applies only where the published sentence names extra headers.** That is
CEC-1306B and CEC-1308C today. Applicability is read off the transcribed quote
rather than a hard-coded list of profile identifiers, so the rule cannot
outlive the text it rests on: if the transcription is corrected, or a document
is reissued with different wording, the rule follows.

**On the other three forms the advisory stays**, and now says which absence it
is asserting: that the instructions for that form do not mention extra header
rows. Same observation, different report, because the published record differs
between the documents.

The detection is unchanged and stays deliberately narrow: an exact copy of the
published header, field for field. "Extra headers" plainly covers more than
that, a title row above the header for instance, but only the exact copy can
be identified without guessing, and QP005 already records what this project
does with a prohibition it cannot test deterministically. QP007 checks the
part it can prove and claims nothing about the rest.

## Consequences

A repeated header row is an error on a CEC-1306B or CEC-1308C filing and an
advisory on the other three. That looks inconsistent and it is: the
inconsistency is in the published documents, and reproducing it is the same
commitment ADR 0002 makes about the two header typos. The tool's job is to
predict what the portal will accept, and the only evidence about that is what
each document says.

A filer who runs both a 1306A and a 1306B file through the tool will see the
same row treated two ways. The QP007 message quotes the rule it rests on and
the advisory says the instructions for its form are silent, so the difference
is explained where it appears rather than only here.

QP007 fires on a row that also produces a handful of field errors, because the
header text lands in Year, Month and County Number columns that reject it.
Those findings are left in place. The QP007 message names the one row to
delete and says that deleting it clears them.
