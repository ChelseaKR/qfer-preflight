"""Form profiles for the QFER Consumption reports.

Each profile describes one CEC report template: the exact header line the
Data Submission Portal expects, which columns carry which published code set,
and the regulation the form cites as its authority.

The header tuples in this module are transcribed byte for byte from the CSV
templates published on the CEC QFER page. They are not normalised, corrected
or tidied. Two of the published headers contain irregularities:

  * CEC-1306A Schedule 1 spells its seventh column "NumberofCustomers" with a
    lower case "o", while every other template spells the same concept
    "NumberOfCustomers".
  * CEC-1306A Schedule 2 spells its fourth column "RetailRatClass", which
    appears to be a typo for "RetailRateClass" in the published template.

Both are reproduced exactly as published, because the goal of this tool is to
tell a filer whether their file matches what the portal will receive, not
whether it matches what the template ought to have said.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model import Citation

QFER_PROGRAM_URL = (
    "https://www.energy.ca.gov/rules-and-regulations/energy-suppliers-reporting"
    "/quarterly-fuel-and-energy-reporting-qfer"
)

_FILES_BASE = "https://www.energy.ca.gov/sites/default/files/2025-07"

INSTRUCTIONS_1306A = f"{_FILES_BASE}/1306A_Instructions_07142025_ada.pdf"
INSTRUCTIONS_1306B = f"{_FILES_BASE}/1306B_Instructions_07142025_ada.pdf"
INSTRUCTIONS_1308B = f"{_FILES_BASE}/1308B_Instructions_07142025_ada.pdf"
INSTRUCTIONS_1308C = f"{_FILES_BASE}/1308C_Instructions_07142025_ada.pdf"

TEMPLATE_1306A_S1 = f"{_FILES_BASE}/1306A_S1_template.csv"
TEMPLATE_1306A_S2 = f"{_FILES_BASE}/1306A_S2_template.csv"
TEMPLATE_1306B = f"{_FILES_BASE}/1306B_template.csv"
TEMPLATE_1308B_S1 = f"{_FILES_BASE}/1308B_S1_template.csv"
TEMPLATE_1308C = f"{_FILES_BASE}/1308C_template.csv"

# The slide deck from the Commission's June 24, 2025 workshop introducing the
# Data Submission Portal. It is a published CEC document, linked from the QFER
# program page, and it states several submission rules that the instruction
# PDFs do not. Where the two disagree, see ADR 0003.
WORKSHOP_DECK_URL = (
    "https://www.energy.ca.gov/sites/default/files/2025-06/QFER_DSP_Workshop_ada.pdf"
)
WORKSHOP_DECK_NAME = (
    "CEC QFER Consumption Data Submission Portal (DSP) Workshop slides, June 24, 2025"
)


@dataclass(frozen=True, slots=True)
class Profile:
    """One CEC report template."""

    id: str
    title: str
    authority: str
    instructions_url: str
    instructions_name: str
    template_url: str
    header: tuple[str, ...]

    # Column roles. Each is either a column name present in `header` or None
    # when the form does not carry that concept.
    company_number_column: str | None = None
    year_column: str | None = None
    month_column: str | None = None
    quarter_column: str | None = None
    county_column: str | None = None
    naics_column: str | None = None
    customer_type_column: str | None = None
    customer_group_column: str | None = None
    customer_group_values: frozenset[str] = frozenset()
    udc_column: str | None = None
    rate_code_column: str | None = None

    # Columns the instructions mark with the shared footnote requiring "0"
    # rather than a blank, "NULL" or "-", and forbidding non numeric
    # characters such as letters, spaces, comma separators and dollar signs.
    numeric_columns: tuple[str, ...] = ()

    def citation(self, locator: str) -> Citation:
        return Citation(
            source=self.instructions_name,
            url=self.instructions_url,
            locator=locator,
            authority=self.authority,
        )

    def template_citation(self, locator: str) -> Citation:
        return Citation(
            source=f"{self.id} published CSV template",
            url=self.template_url,
            locator=locator,
            authority=self.authority,
        )

    def workshop_citation(self, locator: str) -> Citation:
        return Citation(
            source=WORKSHOP_DECK_NAME,
            url=WORKSHOP_DECK_URL,
            locator=locator,
            authority=self.authority,
        )

    def citation_for(self, source: str, locator: str) -> Citation:
        """Build a citation against one of the three published sources."""
        builders = {
            "instructions": self.citation,
            "template": self.template_citation,
            "workshop": self.workshop_citation,
        }
        if source not in builders:  # pragma: no cover
            raise ValueError(f"unknown citation source {source!r}")
        return builders[source](locator)

    def index_of(self, column: str) -> int:
        return self.header.index(column)


# Imported here to avoid a circular import at module definition time.
from .codes import ELECTRIC_CUSTOMER_GROUPS, GAS_CUSTOMER_GROUPS  # noqa: E402

PROFILE_1306A_S1 = Profile(
    id="CEC-1306A-S1",
    title="CEC-1306A Schedule 1, UDC Electricity Sales and Deliveries Quarterly Report",
    authority="California Code of Regulations, Title 20, Section 1306(a)",
    instructions_url=INSTRUCTIONS_1306A,
    instructions_name="CEC-1306A instructions (rev. 07/14/2025)",
    template_url=TEMPLATE_1306A_S1,
    header=(
        "CompanyNumber",
        "Year",
        "Month",
        "CountyNumber",
        "CustomerType",
        "RateClass",
        "NAICSCode",
        "NumberofCustomers",
        "SalesDeliveryAmount",
        "Revenue",
    ),
    company_number_column="CompanyNumber",
    year_column="Year",
    month_column="Month",
    county_column="CountyNumber",
    naics_column="NAICSCode",
    customer_type_column="CustomerType",
    numeric_columns=("NumberofCustomers", "SalesDeliveryAmount", "Revenue"),
)

PROFILE_1306A_S2 = Profile(
    id="CEC-1306A-S2",
    title="CEC-1306A Schedule 2, UDC Retail Rate Description Quarterly Report",
    authority="California Code of Regulations, Title 20, Section 1306(a)",
    instructions_url=INSTRUCTIONS_1306A,
    instructions_name="CEC-1306A instructions (rev. 07/14/2025)",
    template_url=TEMPLATE_1306A_S2,
    header=(
        "CompanyNumber",
        "Year",
        "QuarterNumber",
        "RetailRatClass",
        "Description",
    ),
    company_number_column="CompanyNumber",
    year_column="Year",
    quarter_column="QuarterNumber",
)

PROFILE_1306B = Profile(
    id="CEC-1306B",
    title="CEC-1306B, LSE Quarterly Report",
    authority="California Code of Regulations, Title 20, Section 1306(b)",
    instructions_url=INSTRUCTIONS_1306B,
    instructions_name="CEC-1306B instructions (rev. 07/14/2025)",
    template_url=TEMPLATE_1306B,
    header=(
        "CompanyNumber",
        "Year",
        "MonthNumber",
        "UtilityDeliveryCompany",
        "CustomerGroup",
        "CountyNumber",
        "NumberOfCustomers",
        "SalesAmount",
        "Revenue",
    ),
    company_number_column="CompanyNumber",
    year_column="Year",
    month_column="MonthNumber",
    county_column="CountyNumber",
    customer_group_column="CustomerGroup",
    customer_group_values=ELECTRIC_CUSTOMER_GROUPS,
    udc_column="UtilityDeliveryCompany",
    numeric_columns=("NumberOfCustomers", "SalesAmount", "Revenue"),
)

PROFILE_1308B_S1 = Profile(
    id="CEC-1308B-S1",
    title="CEC-1308B Schedule 1, Gas Utility Deliveries and Revenue Quarterly Report",
    authority=("California Code of Regulations, Title 20, Section 1308(c) and 1307(b)"),
    instructions_url=INSTRUCTIONS_1308B,
    instructions_name="CEC-1308B instructions (rev. 07/14/2025)",
    template_url=TEMPLATE_1308B_S1,
    header=(
        "CompanyNumber",
        "Year",
        "MonthNumber",
        "CountyNumber",
        "NAICSCode",
        "RateCode",
        "NumberOfCustomers",
        "DeliveryVolume",
        "Revenue",
    ),
    company_number_column="CompanyNumber",
    year_column="Year",
    month_column="MonthNumber",
    county_column="CountyNumber",
    naics_column="NAICSCode",
    rate_code_column="RateCode",
    numeric_columns=("NumberOfCustomers", "DeliveryVolume", "Revenue"),
)

PROFILE_1308C = Profile(
    id="CEC-1308C",
    title="CEC-1308C, Gas Retailer Quarterly Report",
    authority=("California Code of Regulations, Title 20, Division 2, Section 1307(a)"),
    instructions_url=INSTRUCTIONS_1308C,
    instructions_name="CEC-1308C instructions (rev. 07/14/2025)",
    template_url=TEMPLATE_1308C,
    header=(
        "CompanyNumber",
        "Year",
        "Month",
        "CountyNumber",
        "CustomerGroup",
        "NumberOfCustomers",
        "SalesDelivery",
        "Revenue",
    ),
    company_number_column="CompanyNumber",
    year_column="Year",
    month_column="Month",
    county_column="CountyNumber",
    customer_group_column="CustomerGroup",
    customer_group_values=GAS_CUSTOMER_GROUPS,
    numeric_columns=("NumberOfCustomers", "SalesDelivery", "Revenue"),
)

PROFILES: Mapping[str, Profile] = {
    p.id: p
    for p in (
        PROFILE_1306A_S1,
        PROFILE_1306A_S2,
        PROFILE_1306B,
        PROFILE_1308B_S1,
        PROFILE_1308C,
    )
}


def get_profile(profile_id: str) -> Profile:
    """Look up a profile by id, case insensitively."""
    wanted = profile_id.strip().upper()
    for pid, profile in PROFILES.items():
        if pid.upper() == wanted:
            return profile
    known = ", ".join(sorted(PROFILES))
    raise KeyError(f"unknown profile {profile_id!r}; known profiles: {known}")
