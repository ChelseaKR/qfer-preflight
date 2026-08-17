# 0005. Customer Type "O" re-examined, and held

- Status: Accepted
- Date: 2026-08-17
- Confirms: ADR 0003

## Context

ADR 0003 declined to report Customer Type `O` as an error, because the DSP
workshop deck of June 24, 2025 lists it and the CEC-1306A instructions of
July 14, 2025 do not. It produces QP025, an informational note, instead.

That decision rested on an argument, not on evidence: that a false alarm
against the one filer entitled to use `O` is worse than a missed error. The
obvious objection was never tested. The instructions were revised three weeks
after the deck. If the Commission had looked at `O` and deliberately withdrawn
it, the deck would be a superseded draft and the tool would be excusing a
value the current instructions have deliberately removed. On that reading the
right answer is a QP014 error, and ADR 0003's Customer Type half is wrong.

So the published record was searched for evidence of withdrawal.

## Decision

**The call holds. `O` remains QP025 at informational severity, and QP014 does
not fire on it.** The search found no evidence of withdrawal, and found
affirmative evidence pointing the other way.

**There is no revision history to withdraw anything in.** The July 14, 2025
instructions carry no change log, no errata, no "what changed" section and no
printed revision date; the date exists only in the filename. Nor do the three
sibling instruction documents reissued the same day. This document family does
not record its own changes, so silence in it carries no signal either way.

**`O` was never in the instructions, so the July revision did not remove it.**
This is the finding that settles the question. The previous published revision
of the CEC-1306A instructions, which the Commission's Forms and Instructions
page still linked in May 2025 and which remains live at
<https://www.energy.ca.gov/sites/default/files/2020-08/1306A_Instructions_ada.pdf>,
reads:

> 4. Customer Type. D = Direct Access Customer. B = Bundled Customer.

Two values. The pre-portal Excel form, still published as the CEC-1306A form,
carries the same pair in its embedded instructions:

> 5. Customer Type
> Default to "B" for Bundled customer. Please use "D" to denote Direct Access
> customer.

So the sequence of published instructions runs B and D, then B, D and C. The
net change made on July 14, 2025 was to **add** C. `O` has never appeared in
any revision of the instructions, which means the July document cannot have
withdrawn it. It can only have gone on not mentioning it, which is what the
document before it did too.

That also disposes of the "superseded draft" reading of the deck. Slide 9
lists its four values under the heading "Updated formatting/validations", as
new portal behaviour rather than as a restatement of the instructions, and the
instructions that followed did not contradict it. They added one of the deck's
four values and stayed silent on another.

**Nothing published since says otherwise.** No later workshop deck exists. No
errata or corrections notice was found. The current QFER program page carries
roughly fifteen frequently asked questions, none of which mentions Customer
Type or its valid values. The June 24 workshop was a staff workshop with no
docket number and no e-comment instructions, so there are no filed comments or
staff responses to search. The deck itself has never been taken down or
annotated: the program page's own FAQ still directs submitters to it.

**And the list that would answer this is still not published.** Slide 44
promises a data dictionary of "expected data types and lists of valid values
for fields that have common errors (e.g., NAICS code, county number, customer
type, UDC name, etc.)", available in July 2025. It has not appeared on the
program page in any snapshot since, and it does not appear there now. It sits
behind the portal's authentication, alongside the "Valid NAICS codes" list
QP018 needs. The same missing document would settle both questions.

One thing worth naming as reasoning rather than evidence: the previous
instructions omitted C, though community choice aggregators had been serving
California load for well over a decade before that revision. The instructions
have historically enumerated fewer codes than were in use. That argues against
reading their silence on `O` as a decision, and equally against treating them
as a complete enumeration. It is an argument, not a citation, and it is not
what this ADR rests on.

## Consequences

ADR 0003 stands unamended, on better footing than it had. Its Customer Type
half was a judgment call about which of two documents to believe; it is now a
judgment call supported by the observation that the two documents were never
actually in conflict about `O`. One lists it, the other has never listed it,
and no published text has ever called it wrong.

QP025's wording is unchanged in substance and now tells a filer what to do:
nothing, unless they file for BART, in which case confirm with the Commission
before submitting.

The reversal condition is narrower than it was, and worth writing down. The
call flips to a QP014 error only on published text stating that `O` is not
accepted. The data dictionary from slide 44 would be that text if it omits
`O` while enumerating the field, since it is the document the deck itself
names as authoritative for valid values. A filer who has portal access can
settle this in a minute; this project cannot.
