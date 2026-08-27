# 0009. Authoritative answers that cannot be cited

- Status: Accepted
- Date: 2026-08-26
- Confirms: ADR 0003, ADR 0005, ADR 0008

## Context

Three open questions in this project named the same document as the thing that
would settle them: the data dictionary promised on slide 44 of the June 24,
2025 DSP workshop deck, "showing expected data types and lists of valid values
for fields that have common errors (e.g., NAICS code, county number, customer
type, UDC name, etc.)".

- QP018 is unevaluated because the "Valid NAICS codes" list it needs is not
  published. Its promotion condition names that data dictionary.
- ADR 0005 held Customer Type `O` at an informational note. Its reversal
  condition names that data dictionary.
- ADR 0008 held a zero padded County Number at a warning. Its reversal
  condition names that data dictionary.

All three were written on the assumption that the document would eventually
appear, because slide 44 says it was to be posted in July 2025. That
assumption was never tested against the Commission itself.

On 2026-08-17 this project's author wrote to the Commission's QFER Consumption
mailbox: where is the "Valid NAICS codes" list published, does the portal
accept a zero padded County Number, and is Customer Type `O` still accepted.
Staff in the Consumption Data Analytics Unit replied over 2026-08-17 to
2026-08-26 and answered all three.

The answers are authoritative. They come from the unit that operates the
portal. They are also private correspondence, published nowhere, readable by
nobody who did not receive them.

## Decision

**Nothing the tool reports changes. The correspondence is recorded, and no
rule cites it.**

The rule this project runs on is not "withhold judgment until the answer is
known". It is "cite, or do not assert". Those come apart for the first time
here, and this ADR is the record of which one governs.

### The data dictionary will not be published

On the NAICS list, staff wrote that "it is currently not posted on a public
website, and we do not plan to do so because the list contains custom NAICS
codes for certain utilities and CEC-defined classification codes for internal
use." On the data dictionary itself: "this is a sensitive internal business
deliverable, and we are not allowed to share it with the public."

So the promotion condition on QP018 and the reversal conditions in ADR 0005
and ADR 0008 are not pending. They are declined at the source. The route each
of them named is closed, and closed deliberately rather than by neglect.

This matters to a reader more than it changes any behaviour. An unevaluated
rule whose promotion condition might be met next quarter and one whose
publisher has said it never will be are not in the same state, and reporting
them identically would be exactly the small dishonesty this project exists to
avoid. QP018's reason text now says which of the two it is. The rule stays
registered, stays unevaluated, and keeps reporting itself on every run.

Its promotion condition is not withdrawn, only narrowed to what it always
should have said: the list published at a URL a reader can retrieve. Any
publication would do. None is expected.

### The portal rejects a padded County Number, and QP024 stays a warning

Staff answered the county question directly: "only integer values of 1-58 and
00 are accepted. Single-digit county numbers with a leading zero, such as
"07," will generate an error." They added that a county inconsistent with an
agency's history draws a warning rather than an error.

That is the answer ADR 0008 said would flip QP024 into a QP013 error, arriving
by a route ADR 0008 did not contemplate.

**QP024 stays a warning.** A filer cannot open this email. Nor can a future
maintainer, an auditor, or anyone deciding whether to trust a finding. An
error grounded in private correspondence is, from outside the project,
indistinguishable from an invented one: both present a confident claim with
nothing a reader can check behind it. The whole worth of this tool is that the
two are distinguishable. Spending that to sharpen one severity would be a poor
trade, and it would be a trade made silently, since the report has no way to
say "this error rests on something you cannot see".

What does change is the character of the warning. It was provisional, awaiting
a document. It is now permanent, and known to be more lenient than the portal.
That is stated here rather than left for a reader to infer from an unmet
condition that will never be met.

The practical consequence is worth naming plainly, because it is a real cost
to a real filer. Someone who submits `07` after seeing only a warning will be
rejected by the portal. The warning already tells them what to write instead,
and a filer who reads it does not get rejected. The tool is doing what it can
inside its contract, and the residue is a filer who ignores a warning.

One further note, since the words collide. The portal's own model, as staff
describe it, has two levels: an error is a value it will not accept, and a
warning is a valid value that is atypical for the reporting agency, which it
accepts and staff follow up on. This tool's warnings do not mean that. A
warning here means the published record does not support calling the value
wrong. The two vocabularies happen to share a word and are making different
claims, and QP024 is precisely a case where they disagree.

### Customer Type `O` is confirmed accepted

Staff wrote that "currently, only Pacific Gas and Electric report "O," which
stands for BART. If another agency reports "O," it will result in a warning."

QP025 already reports `O` as an informational note that names both published
sources and tells a filer to do nothing unless they file for BART. ADR 0005
reached that by argument from the published record alone. The argument was
right. Nothing needs to move, and the confirmation is recorded here rather
than folded into the rule, because a rule that cites the deck must go on
citing only the deck.

### The Census list is confirmed to be the wrong list

The README already declined to substitute the federal Census Bureau NAICS list
for the Commission's, on the evidence that the accepted set includes the `RE`
custom codes, which Census does not publish. Staff describe a wider gap than
that: "custom NAICS codes for certain utilities and CEC-defined classification
codes for internal use", meaning per-utility codes as well as the CEC series.

Staff point to <https://www.census.gov/naics/> for the definitions of standard
codes that are neither custom nor CEC-defined. That is a definitions source
for codes already known to be in the set, not the set itself, so it grounds no
rule here and QP018 is not unblocked by it. The roadmap's standing rejection
of the substitution holds, on better evidence than it had.

### The county file defect is confirmed

ADR 0008 recorded that `AGG_CONSUMPTION_ELEC_COUNTY_TBL_ada.xlsx` puts county
number 33 on two 2024 rows labelled IMPERIAL and SAN DIEGO, while numbering
Imperial 13 and San Diego 37 everywhere else, and read those two rows as a
defect in the Commission's file rather than a competing numbering. The
observation was passed on. Staff confirmed it: "The current county consumption
file is accurate, and the error you saw happened in the data transformation
process. It has since been corrected but not yet updated publicly."

So ADR 0008's corroboration of the county code set stands without that
caveat weighing against it, and the manifest entry for that file carries a
hash change with a known cause waiting to happen. When it changes, the cause
is this correction and not a revision to anything cited.

## Consequences

No rule was added or retired, no severity moved, no code set changed, no
citation created. The registry is byte for byte the same set of checks it was.
What changed is the accuracy of the record about why three of those checks
look the way they do.

The correspondence is listed in the README's source list and in the source
manifest, marked as not citable, for the same reason the documents that
grounded nothing are listed: so a later reader knows the ground was covered
rather than skipped. It carries no hash and no retrieval URL, because it is
not retrievable, which is the entire point of the entry.

A rule like "never cite what a reader cannot open" costs nothing until the day
it costs something. This is that day. The price is one severity that the
project now knows is too lenient, reported at the level it can defend, with
the shortfall written down here. That is the cheaper of the two available
mistakes.

The reversal condition on QP024 is unchanged in substance and is restated here
because its named route is now dead: published text stating that a padded
County Number is not accepted. The data dictionary will not be that text. A
revision of the instructions or a later workshop deck could be. Nothing
currently published is, and correspondence never will be.
