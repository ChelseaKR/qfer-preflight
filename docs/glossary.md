# Glossary

Two vocabularies meet in a report from this tool. One belongs to the
Commission's documents: QFER, DSP, UDC, LSE, TEOR, UEG, NAICS. The other
belongs to the tool: rule, finding, advisory, unevaluated rule, verdict. A
reader who confuses the second for the first will misread what a report is
claiming, so both are written down here.

Nothing in this file grounds a rule. Where an entry quotes a published
document it names the document and the section, so the quote can be checked,
but the citations that carry weight are the ones attached to the rules
themselves, which `qfer-preflight rules` prints in full. Where the published
documents this project reads do not define a term, the entry says so rather
than supplying a definition from somewhere else.

## Terms the Commission's documents use

### QFER

Quarterly Fuel and Energy Reporting. The Commission's program page is titled
"Quarterly Fuel and Energy Reporting (QFER) Consumption Data", at
<https://www.energy.ca.gov/rules-and-regulations/energy-suppliers-reporting/quarterly-fuel-and-energy-reporting-qfer>.
It is the program the five forms this tool reads belong to. The instruction
documents use the abbreviation throughout without expanding it; the page
title is where the expansion is published.

### DSP

Data Submission Portal. The Commission's own upload channel, and the
authoritative validator: what it accepts is what counts. The CEC-1308C
instructions, "Where to file", read "California Energy Commission's secure
Data Submission Portal (DSP) website." Each of the other three instruction
documents does the same thing where the portal first appears in it: writes the
full name and puts the initials after it in brackets.

This tool is not the DSP, is not connected to it, and cannot tell you what it
will do with a file. It reports what published text says about the bytes in
front of it, on your machine, before you upload anything.

### UDC

Utility Distribution Company. The CEC-1306A instructions, "Who must file",
Schedule 1, read "A UDC is an electric utility, or a business unit of an
electric utility, that distributes electricity to customers." The CEC-1306B
instructions put it more briefly in the field definition of the same name: "A
UDC is a utility that distributes electricity to customers."

The word appears in two different roles, which is worth keeping apart:

- As the filer of `CEC-1306A`, Schedules 1 and 2.
- As a column value on `CEC-1306B`, where an LSE names the UDC whose
  territory the sales sit in. There the published set is closed to three
  values, PGE, SCE and SDGE, and QP022 checks it.

### LSE

Load Serving Entity. The CEC-1306B instructions, "Purpose", read "This report
provides the quantity of electricity sold by load serving entities (LSEs)
that are not utility distribution companies (UDC)." Its "Who must file" adds
"Each LSE that sells electricity in California and is not a UDC. Examples of
these types of LSEs are energy service providers and community choice
aggregators."

`CEC-1306B` is the LSE form. Its profile title in this tool, "CEC-1306B, LSE
Quarterly Report", is the form's own name.

### TEOR

A published Customer Group value on `CEC-1308C`, glossed in the instructions'
"Customer Group" list as "thermally enhanced oil recovery". It is carried in
`GAS_CUSTOMER_GROUPS` in `codes.py` and checked by QP015, which compares
spelling and capitalisation exactly, because the same section reads
"IMPORTANT: The Customer Group value must be entered exactly as spelled and
capitalized above."

### UEG

The other `CEC-1308C` Customer Group value that is written as an
abbreviation, glossed in the same list as "utility electric generation
(including cogeneration)". Also in `GAS_CUSTOMER_GROUPS`, also checked by
QP015.

A note on how those two entries are quoted. The published list writes
Residential, Commercial, Industrial and Other with an ASCII hyphen between
the value and its gloss, and writes TEOR and UEG with an en dash instead.
This repository carries no en dash anywhere, so what is quoted above is the
gloss text alone rather than the whole line including its separator. The
words are transcribed exactly; the punctuation between value and gloss is not
reproduced. Nothing depends on it: the value QP015 compares is `TEOR`, and
the transcription that matters is the one in `codes.py`.

### NAICS

**The QFER documents this project reads never expand the abbreviation, so
this glossary does not supply an expansion for it.** Four instruction PDFs and
the workshop deck were searched; each uses "NAICS code" as a bare term.

What they do say is quoted in the registry. The CEC-1306A instructions read:

> NAICS code shall describe the primary activity at the location where the
> energy is consumed. NAICS code must be exactly 6-characters in length and
> match the list of "Valid NAICS codes."

Two columns carry it, on `CEC-1306A-S1` and `CEC-1308B-S1`.

Three rules attach to it and they are worth telling apart, because together
they are the clearest example in the project of what a citation can and
cannot buy:

- **QP017** checks the length, which the sentence above states outright.
- **QP023** checks the CEC custom classification codes, which are published
  as tables in the instructions: the residential `RE` series, plus `925190`,
  `221311`, `221312` and `999999`.
- **QP018** would check membership of the "Valid NAICS codes" list itself,
  and does not, because that list is published nowhere this project can
  retrieve. It is registered and reported as unevaluated on every run of
  every form that carries a NAICS column.

The federal Census Bureau list is not a substitute for the Commission's, and
ADR 0009 records why in detail: the Commission's accepted set includes custom
codes for certain utilities alongside CEC-defined codes, which Census does not
publish. So a code can be a real NAICS code and still not be accepted, and
QP017 passing tells you about length and nothing else.

### Company Number

An identifier assigned by the Commission, not chosen by the filer. All five
forms carry it in column A. Three of the four instruction documents open the
field definition with the same sentence, "The identification number assigned
by CEC staff."; the CEC-1308C instructions write "The identification number
of the gas retailer assigned by CEC staff." The four then differ in what they
add, which is why QP033 keys its quote by profile rather than picking one
wording. If you do not know your number, the CEC-1306B instructions say to
contact CEC QFER Consumption staff. QP021 checks it is present and QP033
checks it is written as digits alone.

### Schedule

Some forms publish more than one report shape under one form number, numbered
as schedules. `CEC-1306A` has three; this tool covers Schedules 1 and 2, and
Schedule 3 goes by a separate channel with no published template. `CEC-1308B`
has two; this tool covers Schedule 1 for the same reason. A profile id names
the schedule where there is one: `CEC-1306A-S1`.

## Terms this tool uses

### Rule

A check derived from a published Commission document, carrying that
document's name, its URL, a locator inside it, and a quote transcribed from
it. Rules have permanent identifiers of the form `QP` plus three digits. An
identifier is never renumbered and never reused. `qfer-preflight rules`
prints the registry with every citation and quote.

A rule is the only thing in this tool that may assert a value is wrong,
because it is the only thing that can show you the text it is asserting it
from.

### Finding

One rule firing on one thing in your file, at one of three severities. A
finding names the rule, the cell, the row, the column and the value, and its
message explains what published text expects instead.

Identical findings, meaning the same rule, the same column and the same
message text, are reported as one line carrying the number of rows it stands
for, the first few of them and the last. Nothing is dropped silently: the
line says it was merged and the report says how many merged into how many.
See ADR 0006.

### Severity

Three levels, and the middle one does not mean what the portal means by it.

- **error**: published text says the value is wrong. No published Commission
  document contradicts the finding. Any error makes the verdict `fail`.
- **warning**: the published record does not support calling the value
  wrong, while something published still points the other way. That happens
  in two shapes. Two Commission documents can differ about the value, which
  is QP024, a zero padded County Number. Or the published text can describe
  what a submission should contain without saying that anything else is
  rejected, which is QP030 and QP031, months outside one calendar quarter and
  rows spanning more than one year.
- **info**: a note, where one published document lists a value another does
  not mention. QP025, Customer Type `O`, is the only one today.

The portal's vocabulary is different, and ADR 0009 records the collision:
there, an error is a value the portal will not accept and a warning is a
valid value that is unusual for the reporting agency. Here, a warning means
the published record does not support calling the value wrong. The two are
making different claims with the same word, and QP024 is precisely a case
where they disagree. Read a warning from this tool as "the published
documents do not agree about this", not as "the portal will accept this".

### Advisory

Something the reader noticed, or had to do to the bytes, that **no published
rule covers**. Advisories have codes beginning `ADV-`, carry no severity,
cite no document, and can never be rendered as findings. The code space is
closed: `ADV-BOM`, `ADV-LINE-ENDINGS`, `ADV-FORMULA-CELL`,
`ADV-HIDDEN-CHARACTER` and `ADV-REPEATED-HEADER`, and nothing else can be
constructed.

An advisory exists so that a report is not silent about something real that
has no citation behind it. It says what is in the bytes, what the reader did
about it, and that the published record does not cover it. It keeps the
verdict away from `pass`, so `--strict` fails on one. See ADR 0004.

An advisory never means "this is wrong". It means "this is here, and nothing
published says anything about it".

### Unevaluated rule

A rule this project registered from published text and cannot mechanically
test, listed in every report with the reason and its promotion condition
attached. QP005, QP018, QP032 and QP034 are the four; which of them apply
depends on the form.

The point of registering them is that their absence can never be mistaken for
their passing. A file that violates one comes back looking exactly as good as
a file that does not, so the report says out loud that the check never ran.
See ADR 0001.

### Profile

One published form template, identified by a string such as `CEC-1306A-S1`,
carrying the header row transcribed byte for byte from the published CSV
template, the column roles, and the regulation the form cites. Pass one with
`--profile`, or leave it out and let the header be matched against the five
published templates. Detection accepts exactly one match and refuses to guess
on zero or several.

### Citation

The document, URL, locator and transcribed quote behind a rule. A citation
names something a reader can open. That requirement is why authoritative
private correspondence with Commission staff, which this project has and
which answered three open questions, is recorded and cites nothing. See
ADR 0009.

### Verdict, or status

Three values, and the first one is rarer than it sounds.

- **`pass`**: no errors and every applicable rule was evaluated. Because
  every profile registers at least one rule that can never be evaluated, no
  real filing reaches this.
- **`fail`**: at least one error-level finding.
- **`unvalidated`**: no errors, but something was not reached. A rule went
  unevaluated, or an advisory was raised, or both.

`unvalidated` is the ordinary outcome for a well-formed file. It is not a
complaint about your data. `docs/filer-guide.md` explains what to do with it.
