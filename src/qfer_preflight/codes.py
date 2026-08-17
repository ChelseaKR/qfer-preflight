"""Published code sets used by the QFER Consumption forms.

Every table in this module is transcribed from a primary source document
published by the California Energy Commission. The provenance of each table is
recorded in the docstring above it, including the document and the page or
section it came from.

Nothing in this module may be extended, guessed at, or inferred. If a code set
is referenced by a form but is not published in a document this project can
fetch, it does not belong here. It belongs in the unimplemented rule registry
so the tool reports it as unevaluated.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

# ---------------------------------------------------------------------------
# County numbers
# ---------------------------------------------------------------------------
# Source: "County Numbers and Corresponding Names (for California)", the table
# printed at the end of the CEC-1306A, CEC-1306B, CEC-1308B and CEC-1308C
# instruction documents (all rev. 07/14/2025). The four printings are identical.
#
# The instructions describe the data type as "numeric data type for county
# numbers 1-58 and 99, and text data type for county "00"".
_COUNTY_NAMES: dict[str, str] = {
    "1": "Alameda",
    "2": "Alpine",
    "3": "Amador",
    "4": "Butte",
    "5": "Calaveras",
    "6": "Colusa",
    "7": "Contra Costa",
    "8": "Del Norte",
    "9": "El Dorado",
    "10": "Fresno",
    "11": "Glenn",
    "12": "Humboldt",
    "13": "Imperial",
    "14": "Inyo",
    "15": "Kern",
    "16": "Kings",
    "17": "Lake",
    "18": "Lassen",
    "19": "Los Angeles",
    "20": "Madera",
    "21": "Marin",
    "22": "Mariposa",
    "23": "Mendocino",
    "24": "Merced",
    "25": "Modoc",
    "26": "Mono",
    "27": "Monterey",
    "28": "Napa",
    "29": "Nevada",
    "30": "Orange",
    "31": "Placer",
    "32": "Plumas",
    "33": "Riverside",
    "34": "Sacramento",
    "35": "San Benito",
    "36": "San Bernardino",
    "37": "San Diego",
    "38": "San Francisco",
    "39": "San Joaquin",
    "40": "San Luis Obispo",
    "41": "San Mateo",
    "42": "Santa Barbara",
    "43": "Santa Clara",
    "44": "Santa Cruz",
    "45": "Shasta",
    "46": "Sierra",
    "47": "Siskiyou",
    "48": "Solano",
    "49": "Sonoma",
    "50": "Stanislaus",
    "51": "Sutter",
    "52": "Tehama",
    "53": "Trinity",
    "54": "Tulare",
    "55": "Tuolumne",
    "56": "Ventura",
    "57": "Yolo",
    "58": "Yuba",
    "99": "Multi",
    "00": "Unknown",
}

COUNTY_NAMES: Mapping[str, str] = MappingProxyType(_COUNTY_NAMES)
COUNTY_NUMBERS: frozenset[str] = frozenset(_COUNTY_NAMES)

# The two-character zero-padded spellings of the single-digit counties, "01"
# through "09". These are the only County Number values that can carry a
# leading zero other than "00", which the published table already lists.
#
# Source: the DSP workshop deck (June 24, 2025), slide 19, formatting rule 6:
# "Any Company Number, County Number, and NAICS code values that contain a
# leading 0 (zero) should be formatted as TEXT data type." That sentence tells
# a filer how to preserve a leading zero on a County Number rather than
# treating the value as wrong, so this project does not report one as an error.
# It is still worth flagging, because the published county table writes these
# counties unpadded and every published example does too. See ADR 0003.
_PADDED_COUNTY_NUMBERS: dict[str, str] = {
    f"0{n}": str(n) for n in range(1, 10) if str(n) in _COUNTY_NAMES
}

PADDED_COUNTY_NUMBERS: Mapping[str, str] = MappingProxyType(_PADDED_COUNTY_NUMBERS)

# ---------------------------------------------------------------------------
# Residential CEC Custom Classification Codes
# ---------------------------------------------------------------------------
# Source: "Residential CEC Custom Classification Codes", the table printed at
# the end of the CEC-1306A and CEC-1308B instruction documents
# (rev. 07/14/2025). Both printings are identical.
#
# Transcribed exactly as published. The published table has no RE3100, RE3500,
# RE3600 or RE3800 entry, so this mapping has none either.
_RESIDENTIAL_CLASSIFICATION_CODES: dict[str, str] = {
    "RE0000": "Residential (not further classified)",
    "RE1000": "Individually metered account (type unknown)",
    "RE1100": "Individually metered single family",
    "RE1200": "Individually metered multi-family",
    "RE1300": "Individually metered other",
    "RE1400": "Trailer - Multiples - Master Metered",
    "RE1500": "Trailer - Air Conditioning (Separately Metered)",
    "RE1600": "Trailer - Water Supply (Separately Metered)",
    "RE1700": "Trailer - Outdoor Lighting (Walkway, etc.)",
    "RE1800": "Trailer - Open",
    "RE1900": "Trailer - Other Residential Uses (Swimming Pools, Laundry rooms, etc.)",
    "RE2000": "Master metered accounts (type unknown)",
    "RE2100": "Master metered single family",
    "RE2200": "Master metered multi-family",
    "RE2300": "Master metered other",
    "RE2400": "Apt. - Multiples - Master Metered",
    "RE2500": "Apt. - Air Conditioning (Separately Metered)",
    "RE2600": "Apt. - Water Supply (Separately Metered)",
    "RE2700": "Apt. - Outdoor Lighting (Walkway, etc.)",
    "RE2800": "Apt. - Open",
    "RE2900": "Apt. - Other Residential Uses (Swimming Pools, Laundry rooms, etc.)",
    "RE3000": "Apt. - Residential - Miscellaneous",
    "RE3200": "Apt. - Residential Second Service",
    "RE3300": "Apt. - Public Housing",
    "RE3400": "Apt. - Residential Hotels",
    "RE3700": "Apt. - Outdoor Lighting (Walkway, etc.)",
    "RE3900": "Apt. - Miscellaneous Residential",
}

RESIDENTIAL_CLASSIFICATION_CODES: Mapping[str, str] = MappingProxyType(
    _RESIDENTIAL_CLASSIFICATION_CODES
)

# ---------------------------------------------------------------------------
# CEC custom classification codes for non-residential special cases
# ---------------------------------------------------------------------------
# Source: the table headed "Description / Classification Code" in the
# CEC-1306A and CEC-1308B instruction documents (rev. 07/14/2025), immediately
# below the "NAICS Code" field definition.
_CUSTOM_CLASSIFICATION_CODES: dict[str, str] = {
    "925190": "Streetlighting",
    "221311": "Water pumping, municipal water supply",
    "221312": "Water pumping, agriculture irrigation",
    "999999": "Unclassified",
}

CUSTOM_CLASSIFICATION_CODES: Mapping[str, str] = MappingProxyType(_CUSTOM_CLASSIFICATION_CODES)

# ---------------------------------------------------------------------------
# Gas delivery rate codes (CEC-1308B Schedule 1)
# ---------------------------------------------------------------------------
# Source: the "Rate Code" table in the CEC-1308B instruction document
# (rev. 07/14/2025), Schedule 1 Instructions.
_GAS_RATE_CODES: dict[str, str] = {
    "10": "Sales to core customers, excluding core cogeneration customers",
    "20": "Sales to core cogeneration customers",
    "30": "Sales to noncore customers, excluding noncore cogeneration customers",
    "40": "Sales to noncore cogeneration customers",
    "50": "Transportation to core customers, excluding cogeneration",
    "60": "Transportation to core customers for cogeneration",
    "70": "Transportation to noncore customers, excluding cogeneration",
    "80": "Transportation to noncore customers for cogeneration",
}

GAS_RATE_CODES: Mapping[str, str] = MappingProxyType(_GAS_RATE_CODES)

# ---------------------------------------------------------------------------
# Customer Type (CEC-1306A Schedule 1)
# ---------------------------------------------------------------------------
# Source: CEC-1306A instructions (rev. 07/14/2025), Schedule 1 Instructions,
# "Customer Type": "D = Direct Access Customer, B = Bundled Customer,
# C = Community Choice Aggregation."
_CUSTOMER_TYPES: dict[str, str] = {
    "D": "Direct Access Customer",
    "B": "Bundled Customer",
    "C": "Community Choice Aggregation",
}

CUSTOMER_TYPES: Mapping[str, str] = MappingProxyType(_CUSTOMER_TYPES)

# One further Customer Type appears in the DSP workshop deck (June 24, 2025),
# slide 9: "Valid values for Customer Type (uppercase letter): B (Bundled),
# D (Direct Access), C (Community Choice Aggregator), O (for BART, PGE only)".
#
# The instruction PDF, revised three weeks later, lists only D, B and C. Two
# published CEC documents therefore disagree. This project does not report a
# value as an error when a published source says it is valid, so "O" produces
# an informational finding under QP025 rather than an error under QP014. See
# ADR 0003.
_CUSTOMER_TYPES_WORKSHOP_ONLY: dict[str, str] = {
    "O": "for BART, PGE only",
}

CUSTOMER_TYPES_WORKSHOP_ONLY: Mapping[str, str] = MappingProxyType(_CUSTOMER_TYPES_WORKSHOP_ONLY)

# ---------------------------------------------------------------------------
# Customer Group
# ---------------------------------------------------------------------------
# The two forms that carry a Customer Group column publish different value
# sets. They are kept separate on purpose. Both instruction documents say
# "The Customer Group value must be entered exactly as spelled and capitalized
# above", so comparison is case sensitive.

# Source: CEC-1306B instructions (rev. 07/14/2025), "Customer Group".
ELECTRIC_CUSTOMER_GROUPS: frozenset[str] = frozenset(
    {"Residential", "Commercial", "Industrial", "Other"}
)

# Source: CEC-1308C instructions (rev. 07/14/2025), "Customer Group".
GAS_CUSTOMER_GROUPS: frozenset[str] = frozenset(
    {"Residential", "Commercial", "Industrial", "TEOR", "UEG", "Other"}
)

# ---------------------------------------------------------------------------
# Utility Distribution Company (CEC-1306B)
# ---------------------------------------------------------------------------
# Source: CEC-1306B instructions (rev. 07/14/2025), "Utility Distribution
# Company (UDC)": "IMPORTANT: The only valid UDC values are PGE, SCE, and
# SDGE. Please enter the UDC exactly as spelled out here with no special
# characters, such as "&"."
VALID_UDC_VALUES: frozenset[str] = frozenset({"PGE", "SCE", "SDGE"})

# ---------------------------------------------------------------------------
# Calendar quarters
# ---------------------------------------------------------------------------
# Source: the "When to file" section common to the CEC-1306A, CEC-1306B,
# CEC-1308B and CEC-1308C instructions (rev. 07/14/2025): "Submit monthly data
# for the previous quarter by the 15th of February, May, August, and November."
QUARTER_MONTHS: Mapping[int, tuple[int, ...]] = MappingProxyType(
    {
        1: (1, 2, 3),
        2: (4, 5, 6),
        3: (7, 8, 9),
        4: (10, 11, 12),
    }
)


def quarter_of_month(month: int) -> int:
    """Return the calendar quarter a month number belongs to."""
    if not 1 <= month <= 12:
        raise ValueError(f"month out of range: {month}")
    return (month - 1) // 3 + 1
