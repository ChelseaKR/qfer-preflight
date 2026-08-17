# 0008. County numbers corroborated by a second CEC dataset

- Status: Accepted
- Date: 2026-08-17
- Confirms: ADR 0003

## Context

ADR 0003 declined to report a zero padded County Number such as `07` as an
error. It produces QP024, a warning, instead. That call rested on reading one
sentence, formatting rule 6 on slide 19 of the DSP workshop deck, as telling a
filer how to keep a leading zero rather than as calling the value wrong. The
ADR recorded the reasoning and, by recording it, made it reversible.

The county table itself came from a single place. It is printed at the end of
four instruction documents, but those four printings are identical and were
issued together, so they are one source repeated rather than four sources
agreeing. Nothing independent had ever been checked against it.

One avenue had been closed off. `ecdms.energy.ca.gov`, the Commission's older
Energy Consumption Data Management System, does not resolve. That was
previously read as a transient failure. It is not: the host returns NXDOMAIN
from every resolver tried, because the system is retired. Its successor is the
Commission's Energy Consumption Data Files page, which was not previously
searched.

## Decision

**ADR 0003 stands unamended. `07` remains a QP024 warning and QP013 does not
fire on it.** The reasoning behind it is now stronger, and this ADR records why
and by exactly how much.

Two files were retrieved from
<https://www.energy.ca.gov/files/energy-consumption-data-files> on
2026-08-17 and read directly, and both are now listed in the README's source
list.

**The county code set is corroborated.**
`AGG_CONSUMPTION_ELEC_COUNTY_TBL_ada.xlsx` carries columns YEAR, COUNTY_NUM,
COUNTY_NAME, SECTOR, RNR and GWH across 14,168 data rows covering 1990 to 2024.
It uses exactly 58 distinct county numbers, 1 through 58, and its number to
name mapping agrees with the transcribed table for 57 of them. This is a second
CEC publication, produced by a different programme for a different purpose,
arriving at the same code set. The transcription in `codes.py` is not a
misreading of one document.

**It writes every county number unpadded, and no padded value appears
anywhere.** That is what bears on ADR 0003.

**It does not make padding an error, and the reasons are worth stating
plainly.** Three of them.

First, and decisively, no published source says a filer must not pad. This file
demonstrates a convention. A convention is not a prohibition, and ADR 0003
forbids asserting an error the published record does not support, not merely
one it contradicts.

Second, the absence of padded values in this file is weaker evidence than it
looks. The COUNTY_NUM cells are stored as spreadsheet numbers, not as text, on
all 14,168 rows. A numeric cell cannot carry a leading zero whatever its
publisher intended, so the absence is partly a property of the storage format
and not wholly an editorial choice.

Third, this dataset is not a QFER filing. It is aggregate consumption
reporting. It says nothing about what the submission portal accepts, which is
the question a filer actually has, and it contains neither `00` nor `99`, so it
grounds nothing about either.

**The file is not error free, and that is recorded rather than smoothed over.**
County number 33 is RIVERSIDE on 245 rows. It also appears on exactly two 2024
rows labelled IMPERIAL and SAN DIEGO. The same file numbers Imperial 13 and San
Diego 37 everywhere else, matching the instruction table, so these two rows are
a defect in the CEC's own file rather than evidence of a different numbering.
Reporting the corroboration without this would overstate it.

**QP018 is not unblocked.** The successor page was searched for the "Valid
NAICS codes" list the rule needs. It publishes no NAICS code list, no customer
type list and no rate class list. The SECTOR column in both files holds
descriptive text such as "Agriculture and Water Pumping", not a NAICS code, and
no six digit value appears anywhere in either file. This is a negative result
and it is written down as one, in the README and in the rule's own reason,
so that a later reader knows the ground has been covered rather than skipped.

## Consequences

Nothing the tool does changes. No rule was added, no severity moved, no code
set grew. This ADR adds evidence and a source, and that is all it adds, which
is the honest description of what a corroborating source is worth.

The reversal condition on the county half of ADR 0003 is unchanged and is worth
restating, because corroboration invites the mistake of thinking a question has
been settled when it has only been better supported. QP024 becomes a QP013
error only on published text stating that a padded County Number is not
accepted. The data dictionary named on slide 44 of the workshop deck would be
that text if it enumerates the field and excludes the padded form. Until then a
filer who submits `07` gets a warning saying the published sources differ, and
never an error.

Following ADR 0000, ADR 0003 is not edited. This ADR confirms it, as ADR 0005
does for its Customer Type half.
