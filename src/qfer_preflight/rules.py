"""The rule registry.

Every rule in this file is derived from text published by the California
Energy Commission, and carries a citation to the document it came from. The
`quote` attached to a rule is transcribed from that document. The only
normalisation applied to a quote is that typographic quotation marks are
written as plain ASCII quotation marks. Wording, spelling and punctuation are
otherwise left exactly as published, including in the few places where the
published text contains an evident typo.

Rule identifiers are permanent. QP001 will always mean what it means today.
An identifier is never reassigned to a different check. If a rule is
withdrawn, it keeps its identifier and is marked retired.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from .model import Rule, Severity
from .profiles import Profile

# ---------------------------------------------------------------------------
# Shared quotes, keyed by profile id where the published wording differs.
# "*" supplies the wording used when a profile has no specific entry.
# ---------------------------------------------------------------------------

_EXTRA_INFO_QUOTE: Mapping[str, str] = {
    "CEC-1306A-S1": (
        "Exclude any extra information, including data for other fields, "
        "miscellaneous calculations, blank rows, or totals."
    ),
    "CEC-1306A-S2": (
        "Exclude any extra information, including data for other fields, "
        "miscellaneous calculations, blank rows, or totals."
    ),
    "CEC-1308B-S1": (
        "Exclude any extra information including data for other fields, "
        "miscellaneous calculations, blank rows, or totals."
    ),
    "CEC-1306B": (
        "Exclude any extra information, including extra headers, data for "
        "other fields, miscellaneous calculations, blank rows, or totals."
    ),
    "CEC-1308C": (
        "Exclude any extra information, including extra headers, data for "
        "other fields, miscellaneous calculations, blank rows, or totals."
    ),
}

_ZERO_PLACEHOLDER_QUOTE: Mapping[str, str] = {
    "*": (
        'For values of zero, please enter "0" instead of leaving the cell '
        'blank or entering "NULL" or "-".'
    ),
    "CEC-1308B-S1": (
        'For values of zero, please enter "0" instead of leaving the cell '
        'blank or entering NULL or "-".'
    ),
}

_NON_NUMERIC_QUOTE: Mapping[str, str] = {
    "*": (
        "Do not add any non-numeric characters, such as letters, spaces, "
        "comma separator, dollar sign, etc."
    ),
    # The CEC-1306A instructions read "letter" rather than "letters".
    "CEC-1306A-S1": (
        "Do not add any non-numeric characters, such as letter, spaces, "
        "comma separator, dollar sign, etc."
    ),
    "CEC-1308B-S1": (
        "Do not add any non-numeric characters such as letters, spaces, "
        "comma separator, dollar sign, etc."
    ),
}

_WHEN_TO_FILE_QUOTE = (
    "Submit monthly data for the previous quarter by the 15th of February, "
    "May, August, and November."
)

_NAICS_QUOTE: Mapping[str, str] = {
    "*": (
        "NAICS code shall describe the primary activity at the location where "
        "the energy is consumed. NAICS code must be exactly 6-characters in "
        'length and match the list of "Valid NAICS codes."'
    ),
    # The CEC-1308B instructions add a sentence naming where the list lives.
    "CEC-1308B-S1": (
        "NAICS code shall describe the primary activity at the location where "
        "the energy is consumed. NAICS code must be exactly 6-characters in "
        'length and match the list of "Valid NAICS codes." See list of "Valid '
        'NAICS codes" for identifying which NAICS codes will be accepted by '
        "the DSP."
    ),
}

# Formatting rule 6 from the DSP workshop deck, slide 19. This is the only
# published statement anywhere that contemplates a County Number carrying a
# leading zero, and it tells the filer how to keep the zero rather than calling
# the value wrong. See ADR 0003.
_LEADING_ZERO_QUOTE = (
    "Any Company Number, County Number, and NAICS code values that contain a "
    "leading 0 (zero) should be formatted as TEXT data type."
)

# Slide 9 of the same deck, listing the Customer Type values the portal
# accepts. It carries one value, O, that the instruction PDF does not list.
_CUSTOMER_TYPE_DSP_QUOTE = (
    "Valid values for Customer Type (uppercase letter): B (Bundled), D (Direct "
    "Access), C (Community Choice Aggregator), O (for BART, PGE only)"
)

# The four instruction documents word the Company Number data type
# differently, and CEC-1306B alone adds the sentence that names non-numeric
# characters outright. Each profile carries the wording its own document
# publishes; see ADR 0002 on why they are not merged into one.
_COMPANY_NUMBER_QUOTE: Mapping[str, str] = {
    "CEC-1306A-S1": (
        "The identification number assigned by CEC staff. Column A, numeric "
        "data type, or text data type if Company Number begins with leading zero."
    ),
    # Schedule 2 shares the Schedule 1 document, and the wording there is the
    # same field definition reprinted in it.
    "CEC-1306A-S2": (
        "The identification number assigned by CEC staff. Column A, numeric "
        "data type, or text data type if Company Number begins with leading zero."
    ),
    "CEC-1306B": (
        "The identification number assigned by CEC staff. Please use the same "
        "number contained in the previous submission. Non-numeric characters "
        "(e.g., dashes) must be removed. If you do not know this number or do "
        "not know how to access this number, please contact CEC QFER Consumption "
        "staff. Column A, numeric data type unless your Company Number contains "
        "a leading zero, in which case, text data type."
    ),
    "CEC-1308B-S1": (
        "The identification number assigned by CEC staff. Column A, numeric "
        "data type unless your Company Number contains a leading zero, in which "
        "case, text data type."
    ),
    "CEC-1308C": (
        "The identification number of the gas retailer assigned by CEC staff. "
        "Column A, numeric data type unless your Company Number contains a "
        "leading zero, in which case, text data type."
    ),
}

# Slide 19 of the DSP workshop deck, formatting rule 4. Its second sentence
# names fields whose cells may not be blank or carry non-numeric characters,
# which corroborates QP019 and QP020 on the columns the footnotes already
# cover and extends them to Company Number, now QP033. Its first sentence is
# the ground for QP034, which stays unevaluated for the reason stated there.
_COMMA_AND_BLANK_CELLS_QUOTE = (
    "Do not include commas anywhere in the file. Do not have blank cells or non-"
    "numeric characters in the Company Number, Year, Month, County Number, "
    "Customer Count, Sales, and Revenue fields."
)


def _resolve(source: str | Mapping[str, str] | None, profile_id: str) -> str | None:
    if source is None or isinstance(source, str):
        return source
    if profile_id in source:
        return source[profile_id]
    return source.get("*")


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """A rule definition that is bound to a profile to produce a `Rule`."""

    id: str
    title: str
    severity: Severity
    locator: str | Mapping[str, str]
    applies: Callable[[Profile], bool]
    quote: str | Mapping[str, str] | None = None
    implemented: bool = True
    unimplemented_reason: str | None = None
    # Which published document the citation points at: the instructions PDF
    # for the form, the published CSV template, or the DSP workshop deck.
    cites: str = "instructions"
    tags: tuple[str, ...] = field(default_factory=tuple)

    def bind(self, profile: Profile) -> Rule:
        locator = _resolve(self.locator, profile.id)
        if locator is None:  # pragma: no cover
            raise ValueError(f"rule {self.id} has no locator for {profile.id}")
        citation = profile.citation_for(self.cites, locator)
        return Rule(
            id=self.id,
            title=self.title,
            severity=self.severity,
            citation=citation,
            quote=_resolve(self.quote, profile.id),
            implemented=self.implemented,
            unimplemented_reason=self.unimplemented_reason,
        )


def _always(_: Profile) -> bool:
    return True


# ---------------------------------------------------------------------------
# Structural rules
#
# The identifier sequence has six holes in it: QP008, QP009, and QP026 through
# QP029. None of them has ever been allocated to anything, in any commit on any
# branch in this repository's history, so no rule was withdrawn and none was
# lost. Why the sections were originally spaced to leave that headroom is not
# recorded anywhere, and ADR 0010 says so rather than inventing a reason. The
# six stay unallocated; new rules take the next unused identifier above the
# highest one. tests/test_rules.py holds that list against this registry.
# ---------------------------------------------------------------------------

RULE_SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        id="QP001",
        title="Input must be a non-empty file that parses as CSV",
        severity=Severity.ERROR,
        locator='"How to file", requirement to submit comma-separated values',
        quote="The data must be submitted in a comma-separated values (CSV) format.",
        applies=_always,
        tags=("structural",),
    ),
    RuleSpec(
        id="QP002",
        title="Header row must match the published template exactly, in order",
        severity=Severity.ERROR,
        locator="header row of the published CSV template",
        applies=_always,
        cites="template",
        tags=("structural",),
    ),
    RuleSpec(
        id="QP003",
        title="Every data row must have the same number of fields as the header",
        severity=Severity.ERROR,
        locator='"Important Template Notes" / "Notes: Each data submission shall"',
        quote=_EXTRA_INFO_QUOTE,
        applies=_always,
        tags=("structural",),
    ),
    RuleSpec(
        id="QP004",
        title="Submission must not contain blank rows",
        severity=Severity.ERROR,
        locator='"Important Template Notes" / "Notes: Each data submission shall"',
        quote=_EXTRA_INFO_QUOTE,
        applies=_always,
        tags=("structural",),
    ),
    RuleSpec(
        id="QP005",
        title="Submission must not contain totals or summary rows",
        severity=Severity.ERROR,
        locator='"Important Template Notes" / "Notes: Each data submission shall"',
        quote=_EXTRA_INFO_QUOTE,
        applies=_always,
        implemented=False,
        unimplemented_reason=(
            "The instructions prohibit totals rows but publish no marker that "
            "distinguishes a totals row from a data row. The DSP workshop deck "
            'repeats the prohibition ("Extra rows will not be accepted; only '
            'include required info", slide 19) and illustrates it with a blank '
            "row rather than a totals row, so it adds no marker either. A "
            "totals row that carried a valid company number, year, month and "
            "county would be indistinguishable from data. Any test would be a "
            "heuristic guess, so this rule is registered and left unevaluated "
            "rather than being approximated. Promotion condition: published "
            "text distinguishing a totals row from a data row, for example a "
            "marker the instructions say such a row must carry, or a worked "
            "example of one in a CEC document. No amount of ingenuity about "
            "row shapes substitutes for either."
        ),
        tags=("structural",),
    ),
    RuleSpec(
        id="QP006",
        title="Submission must contain at least one data row",
        severity=Severity.ERROR,
        locator='"Purpose" and "When to file"',
        quote=_WHEN_TO_FILE_QUOTE,
        applies=_always,
        tags=("structural",),
    ),
    RuleSpec(
        id="QP007",
        title="Submission must not repeat the header row among the data",
        severity=Severity.ERROR,
        locator='"Important Template Notes" / "Notes: Each data submission shall"',
        quote=_EXTRA_INFO_QUOTE,
        # Only the two documents whose published sentence names "extra
        # headers". The applicability is read off the transcribed quote rather
        # than a list of profile ids, so the rule cannot outlive the text it
        # rests on: correct the transcription and the rule follows. The other
        # three documents publish the same sentence without those words, and
        # there a duplicated header row stays an advisory. See ADR 0007.
        applies=lambda p: "extra headers" in (_resolve(_EXTRA_INFO_QUOTE, p.id) or ""),
        tags=("structural",),
    ),
    # -----------------------------------------------------------------------
    # Field rules. Begins at QP010, leaving QP008 and QP009 unallocated; see
    # ADR 0010.
    # -----------------------------------------------------------------------
    RuleSpec(
        id="QP010",
        title="Year must be a four-digit calendar year",
        severity=Severity.ERROR,
        locator='field definition "Year"',
        quote="Use four-digit year (e.g., 2025).",
        applies=lambda p: p.year_column is not None,
        tags=("field",),
    ),
    RuleSpec(
        id="QP011",
        title="Month must be a whole number from 1 to 12",
        severity=Severity.ERROR,
        locator='field definition "Month Number"',
        quote="Numeric month (i.e., 1, 2, 3, ..., 12).",
        applies=lambda p: p.month_column is not None,
        tags=("field",),
    ),
    RuleSpec(
        id="QP012",
        title="Quarter Number must be 1, 2, 3 or 4",
        severity=Severity.ERROR,
        locator='Schedule 2 field definition "Quarter Number"',
        quote="Calendar year quarter (i.e., 1, 2, 3, or 4).",
        applies=lambda p: p.quarter_column is not None,
        tags=("field",),
    ),
    RuleSpec(
        id="QP013",
        title="County Number must appear in the published county table",
        severity=Severity.ERROR,
        locator=(
            'field definition "County Number" and the table "County Numbers '
            'and Corresponding Names (for California)"'
        ),
        quote=(
            "Provide the county number where the end-use customer consumed the "
            "reported energy. A table of county numbers and their corresponding "
            "county names is provided at the end of this document."
        ),
        applies=lambda p: p.county_column is not None,
        tags=("field", "codeset"),
    ),
    RuleSpec(
        id="QP014",
        title="Customer Type must be D, B or C",
        severity=Severity.ERROR,
        locator='Schedule 1 field definition "Customer Type"',
        quote=(
            "D = Direct Access Customer, B = Bundled Customer, C = Community Choice Aggregation."
        ),
        applies=lambda p: p.customer_type_column is not None,
        tags=("field", "codeset"),
    ),
    RuleSpec(
        id="QP015",
        title="Customer Group must match a published value, spelled and capitalised exactly",
        severity=Severity.ERROR,
        locator='field definition "Customer Group"',
        quote=(
            "IMPORTANT: The Customer Group value must be entered exactly as "
            "spelled and capitalized above."
        ),
        applies=lambda p: p.customer_group_column is not None,
        tags=("field", "codeset"),
    ),
    RuleSpec(
        id="QP016",
        title="Rate Code must appear in the published gas rate code table",
        severity=Severity.ERROR,
        locator='Schedule 1 field definition "Rate Code"',
        quote=("Use the following rate codes to describe the type of gas delivery."),
        applies=lambda p: p.rate_code_column is not None,
        tags=("field", "codeset"),
    ),
    RuleSpec(
        id="QP017",
        title="NAICS Code must be exactly six characters long",
        severity=Severity.ERROR,
        locator='field definition "NAICS Code"',
        quote=_NAICS_QUOTE,
        applies=lambda p: p.naics_column is not None,
        tags=("field",),
    ),
    RuleSpec(
        id="QP018",
        title='NAICS Code must appear in the CEC "Valid NAICS codes" list',
        severity=Severity.ERROR,
        locator='field definition "NAICS Code"',
        quote=_NAICS_QUOTE,
        applies=lambda p: p.naics_column is not None,
        implemented=False,
        unimplemented_reason=(
            'The instructions require the code to "match the list of Valid '
            'NAICS codes" and direct the filer to see that list, but the '
            "reference resolves to nothing public. The phrase is not a "
            "hyperlink in either instruction PDF, neither PDF carries a NAICS "
            "appendix, and the list appears at no URL on energy.ca.gov that "
            "this project could retrieve. The search for a published copy is "
            "closed rather than unfinished. The last unexplored avenue was the "
            "Commission's older Energy Consumption Data Management System, "
            "whose host does not resolve because the system is retired, not "
            "because of any transient fault. Its successor, the Energy "
            "Consumption Data Files page, was retrieved and read on "
            "2026-08-17: it publishes no NAICS code list, no customer type "
            "list and no rate class list, its SECTOR column holds descriptive "
            'text such as "Agriculture and Water Pumping" rather than a code, '
            "and no six digit value appears anywhere in it. The workshop deck "
            'places the list in a "data dictionary showing expected data types '
            'and lists of valid values", to be posted on the portal app '
            "landing pages, which sit behind authentication, or obtained by "
            "emailing Commission staff. Neither route yields a document "
            "published at a URL this project can cite. The list is also not "
            "simply the federal Census Bureau list, since the Commission's own "
            "accepted set includes its RE custom codes, which are not Census "
            "codes. Membership is therefore not checked. Length is still "
            "checked, by QP017, and the CEC custom classification codes are "
            "still checked, by QP023. The Commission was then asked "
            "directly, and answered on 2026-08-26 that the list is not posted "
            "on a public website, that there is no plan to post it because it "
            "carries custom NAICS codes for certain utilities alongside "
            "CEC-defined codes for internal use, and that the data dictionary "
            "holding it is an internal deliverable staff are not permitted to "
            "share publicly. That confirms the Census substitution would be "
            "wrong, since per-utility custom codes are not Census codes, and "
            "it moves this rule's promotion condition from pending to "
            "declined at the source. See ADR 0009. Promotion condition, "
            "unchanged in substance and not expected to be met: the list "
            "published at a URL this project can retrieve, after which "
            "transcribing it into codes.py with provenance and implementing "
            "membership is a transcription job. A copy obtained behind portal "
            "authentication, by emailing staff, or in correspondence does not "
            "qualify: a citation in this project names a source a reader can "
            "check without an account."
        ),
        tags=("field", "codeset"),
    ),
    RuleSpec(
        id="QP019",
        title='Numeric fields must carry "0" rather than a blank, "NULL" or "-"',
        severity=Severity.ERROR,
        locator="footnote to the numeric field definitions, note (1)",
        quote=_ZERO_PLACEHOLDER_QUOTE,
        applies=lambda p: bool(p.numeric_columns),
        tags=("field",),
    ),
    RuleSpec(
        id="QP020",
        title="Numeric fields must not contain non-numeric characters",
        severity=Severity.ERROR,
        locator="footnote to the numeric field definitions, note (2)",
        quote=_NON_NUMERIC_QUOTE,
        applies=lambda p: bool(p.numeric_columns),
        tags=("field",),
    ),
    RuleSpec(
        id="QP021",
        title="Company Number must be present on every row",
        severity=Severity.ERROR,
        locator='field definition "Company Number"',
        quote="The identification number assigned by CEC staff.",
        applies=lambda p: p.company_number_column is not None,
        tags=("field",),
    ),
    RuleSpec(
        id="QP022",
        title="Utility Distribution Company must be PGE, SCE or SDGE",
        severity=Severity.ERROR,
        locator='field definition "Utility Distribution Company (UDC)"',
        quote=(
            "IMPORTANT: The only valid UDC values are PGE, SCE, and SDGE. "
            "Please enter the UDC exactly as spelled out here with no special "
            'characters, such as "&".'
        ),
        applies=lambda p: p.udc_column is not None,
        tags=("field", "codeset"),
    ),
    RuleSpec(
        id="QP023",
        title="A residential classification code must appear in the published RE code table",
        severity=Severity.ERROR,
        locator=(
            'the table "Residential CEC Custom Classification Codes" and the '
            "CEC custom classification code table below the NAICS Code "
            "field definition"
        ),
        quote=(
            "For residential, streetlighting, water pump and unclassified "
            "customers, please use the following CEC custom classification codes."
        ),
        applies=lambda p: p.naics_column is not None,
        tags=("field", "codeset"),
    ),
    RuleSpec(
        id="QP024",
        title="County Number should be written without a leading zero, as the published table writes it",
        severity=Severity.WARNING,
        locator='slide 19, "Formatting Rules (3/3)", rule 6',
        quote=_LEADING_ZERO_QUOTE,
        applies=lambda p: p.county_column is not None,
        cites="workshop",
        tags=("field", "codeset"),
    ),
    RuleSpec(
        id="QP025",
        title='Customer Type "O" is published in the workshop deck but not in the instructions',
        severity=Severity.INFO,
        locator=(
            'slide 9, "1306A UDC Electricity Sales/Deliveries Quarterly '
            'Report, Schedule 1", Updated formatting/validations'
        ),
        quote=_CUSTOMER_TYPE_DSP_QUOTE,
        applies=lambda p: p.customer_type_column is not None,
        cites="workshop",
        tags=("field", "codeset"),
    ),
    # -----------------------------------------------------------------------
    # Cross-row rules. Begins at QP030, leaving QP026 through QP029
    # unallocated; see ADR 0010.
    # -----------------------------------------------------------------------
    RuleSpec(
        id="QP030",
        title="All months in a submission should fall within one calendar quarter",
        severity=Severity.WARNING,
        locator='"When to file"',
        quote=_WHEN_TO_FILE_QUOTE,
        applies=lambda p: p.month_column is not None,
        tags=("cross-row",),
    ),
    RuleSpec(
        id="QP031",
        title="All rows in a submission should carry the same reporting year",
        severity=Severity.WARNING,
        locator='"When to file"',
        quote=_WHEN_TO_FILE_QUOTE,
        applies=lambda p: p.year_column is not None,
        tags=("cross-row",),
    ),
    RuleSpec(
        id="QP032",
        title="A submission should not repeat the same reporting key twice",
        severity=Severity.WARNING,
        locator='"Important Template Notes" / "Notes: Each data submission shall"',
        quote=_EXTRA_INFO_QUOTE,
        applies=_always,
        implemented=False,
        unimplemented_reason=(
            "No published document states which combination of columns forms "
            "the unique reporting key for a row. The CEC's own worked example, "
            "on slide 19 of the DSP workshop deck, settles it the other way: "
            "two of its rows carry identical Company Number, Year, Month, "
            "County Number, Customer Type, Rate Class and NAICS Code and "
            "differ only in the reported amounts, and the slide marks only the "
            "blank row as wrong. Legitimate repeats therefore exist, the tool "
            "cannot tell one from a duplicate, and choosing a key would be an "
            "invention. The only duplicate rule published anywhere applies to "
            "whole submissions rather than rows: the portal refuses a second "
            'submission for the same entity and period ("This entity has '
            'already submitted for this year and period", slide 35). '
            "Promotion condition: published text naming the columns that form "
            "a row's unique reporting key, or published text acknowledging "
            "that legitimate repeats exist and bounding what they may repeat. "
            "Either would let the check be written without choosing a key by "
            "inference."
        ),
        tags=("cross-row",),
    ),
    RuleSpec(
        id="QP033",
        title="Company Number must be written as digits alone",
        severity=Severity.ERROR,
        locator='field definition "Company Number"',
        quote=_COMPANY_NUMBER_QUOTE,
        applies=lambda p: p.company_number_column is not None,
        tags=("field",),
    ),
    RuleSpec(
        id="QP034",
        title="No commas may appear anywhere in the file",
        severity=Severity.ERROR,
        locator='slide 19, "Formatting Rules (2/3)", rule 4',
        quote=_COMMA_AND_BLANK_CELLS_QUOTE,
        cites="workshop",
        applies=_always,
        implemented=False,
        unimplemented_reason=(
            'The workshop deck says to "not include commas anywhere in the '
            'file". Taken literally that rejects every CSV the portal itself '
            "defines, because the comma is the delimiter the published "
            "templates are written in. The narrower reading, that no value may "
            "contain a comma character, would be an interpretation rather than "
            "a published test, and no instruction document repeats the "
            "sentence. Any test here would rest on choosing between those "
            "readings, so this rule is registered and left unevaluated rather "
            "than approximated. What is mechanical in the same sentence is "
            "checked elsewhere: blank cells and non-numeric characters in the "
            "named fields are QP019 and QP020 on the numeric columns, and "
            "Company Number's form is QP033."
        ),
        tags=("structural",),
    ),
)


RULE_SPECS_BY_ID: Mapping[str, RuleSpec] = {spec.id: spec for spec in RULE_SPECS}


def specs_for(profile: Profile) -> tuple[RuleSpec, ...]:
    """Return the rule specs that apply to a profile, in registry order."""
    return tuple(spec for spec in RULE_SPECS if spec.applies(profile))


def rules_for(profile: Profile) -> tuple[Rule, ...]:
    """Return the bound rules that apply to a profile, in registry order."""
    return tuple(spec.bind(profile) for spec in specs_for(profile))
