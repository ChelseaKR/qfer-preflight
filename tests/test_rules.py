"""Rule-by-rule behaviour, and the integrity of the registry itself."""

from __future__ import annotations

from pathlib import Path

import pytest

from qfer_preflight.codes import (
    COUNTY_NAMES,
    COUNTY_NUMBERS,
    CUSTOMER_TYPES,
    CUSTOMER_TYPES_WORKSHOP_ONLY,
    GAS_RATE_CODES,
    PADDED_COUNTY_NUMBERS,
    RESIDENTIAL_CLASSIFICATION_CODES,
    quarter_of_month,
)
from qfer_preflight.engine import validate_bytes, validate_path
from qfer_preflight.model import Report, Severity
from qfer_preflight.profiles import (
    PROFILE_1306A_S1,
    PROFILE_1306B,
    PROFILE_1308B_S1,
    PROFILE_1308C,
    PROFILES,
    WORKSHOP_DECK_URL,
    Profile,
    get_profile,
)
from qfer_preflight.rules import RULE_SPECS, rules_for, specs_for

FIXTURES = Path(__file__).parent / "fixtures"


def _rows(profile: Profile, *data_rows: str) -> bytes:
    header = ",".join(profile.header)
    return ("\r\n".join([header, *data_rows]) + "\r\n").encode()


def _fired(report: Report) -> set[str]:
    return {f.rule_id for f in report.findings}


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------


def test_rule_ids_are_unique() -> None:
    ids = [spec.id for spec in RULE_SPECS]
    assert len(ids) == len(set(ids))


def test_every_rule_carries_a_citation_with_a_real_url() -> None:
    for profile in PROFILES.values():
        for rule in rules_for(profile):
            assert rule.citation.url.startswith("https://www.energy.ca.gov/")
            assert rule.citation.source
            assert rule.citation.locator
            assert rule.citation.authority


def test_every_unimplemented_rule_explains_itself() -> None:
    for spec in RULE_SPECS:
        if not spec.implemented:
            assert spec.unimplemented_reason
            assert len(spec.unimplemented_reason) > 40


def test_rule_ids_follow_the_stable_scheme() -> None:
    for spec in RULE_SPECS:
        assert spec.id.startswith("QP")
        assert spec.id[2:].isdigit()
        assert len(spec.id) == 5


def test_every_rule_cites_one_of_the_three_published_sources() -> None:
    for spec in RULE_SPECS:
        assert spec.cites in {"instructions", "template", "workshop"}


def test_workshop_cited_rules_point_at_the_workshop_deck() -> None:
    for spec in RULE_SPECS:
        if spec.cites != "workshop":
            continue
        for profile in PROFILES.values():
            if spec.applies(profile):
                assert spec.bind(profile).citation.url == WORKSHOP_DECK_URL


def test_the_two_customer_type_tables_do_not_overlap() -> None:
    """A value belongs to one published source or the other, never both."""
    assert not set(CUSTOMER_TYPES) & set(CUSTOMER_TYPES_WORKSHOP_ONLY)


def test_no_dash_characters_in_published_quotes() -> None:
    """Quotes are transcribed; they must not acquire typographic dashes."""
    for spec in RULE_SPECS:
        for profile in PROFILES.values():
            if not spec.applies(profile):
                continue
            rule = spec.bind(profile)
            for text in (rule.title, rule.quote or "", rule.citation.locator):
                assert "\u2014" not in text  # em dash
                assert "\u2013" not in text  # en dash


# ---------------------------------------------------------------------------
# Published code sets
# ---------------------------------------------------------------------------


def test_county_table_matches_the_published_shape() -> None:
    assert len(COUNTY_NUMBERS) == 60  # 58 counties, plus Multi and Unknown
    assert COUNTY_NAMES["34"] == "Sacramento"
    assert COUNTY_NAMES["99"] == "Multi"
    assert COUNTY_NAMES["00"] == "Unknown"
    for n in range(1, 59):
        assert str(n) in COUNTY_NUMBERS


def test_residential_codes_have_no_invented_entries() -> None:
    # The published table skips these; the transcription must skip them too.
    for absent in ("RE3100", "RE3500", "RE3600", "RE3800"):
        assert absent not in RESIDENTIAL_CLASSIFICATION_CODES
    assert len(RESIDENTIAL_CLASSIFICATION_CODES) == 27


def test_gas_rate_codes_are_the_published_eight() -> None:
    assert sorted(GAS_RATE_CODES) == ["10", "20", "30", "40", "50", "60", "70", "80"]


@pytest.mark.parametrize(
    "month,quarter", [(1, 1), (3, 1), (4, 2), (6, 2), (7, 3), (9, 3), (10, 4), (12, 4)]
)
def test_quarter_of_month(month: int, quarter: int) -> None:
    assert quarter_of_month(month) == quarter


def test_quarter_of_month_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        quarter_of_month(13)


# ---------------------------------------------------------------------------
# Field rules
# ---------------------------------------------------------------------------


def test_clean_1306a_row_produces_no_findings() -> None:
    report = validate_path(str(FIXTURES / "1306a_s1_clean.csv"), PROFILE_1306A_S1)
    assert report.findings == []
    assert report.rows_read == 3


@pytest.mark.parametrize(
    "fixture,profile_id",
    [
        ("1306b_clean.csv", "CEC-1306B"),
        ("1308b_s1_clean.csv", "CEC-1308B-S1"),
        ("1308c_clean.csv", "CEC-1308C"),
    ],
)
def test_other_profiles_accept_their_clean_fixtures(fixture: str, profile_id: str) -> None:
    report = validate_path(str(FIXTURES / fixture), get_profile(profile_id))
    assert report.findings == [], [f.message for f in report.findings]


def test_dirty_fixture_fires_the_expected_rules() -> None:
    report = validate_path(str(FIXTURES / "1306a_s1_dirty.csv"), PROFILE_1306A_S1)
    fired = _fired(report)
    for expected in (
        "QP004",  # blank row
        "QP010",  # two-digit year
        "QP011",  # month 13
        "QP013",  # county 77
        "QP014",  # customer type X
        "QP019",  # NULL in a numeric field
        "QP020",  # "1,234" and "$500"
        "QP021",  # empty company number
        "QP023",  # RE9999 is not published
    ):
        assert expected in fired, f"{expected} should have fired; got {sorted(fired)}"


def test_naics_length_rule() -> None:
    data = _rows(PROFILE_1306A_S1, "1,2025,1,1,B,A1,1234567,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert "QP017" in _fired(report)


def test_naics_custom_code_is_accepted() -> None:
    data = _rows(PROFILE_1306A_S1, "1,2025,1,1,B,A1,221312,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert "QP017" not in _fired(report)
    assert "QP023" not in _fired(report)


# ---------------------------------------------------------------------------
# County numbers, padded and otherwise
#
# The published county table writes 1 to 58 unpadded and only Unknown as "00".
# A filer whose spreadsheet emits "07" is not doing something any published
# source calls an error, so QP024 warns and QP013 stays quiet. See ADR 0003.
# ---------------------------------------------------------------------------


def test_a_zero_padded_county_warns_rather_than_failing() -> None:
    data = _rows(PROFILE_1306A_S1, "1,2025,1,07,B,A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    fired = _fired(report)

    assert "QP024" in fired
    assert "QP013" not in fired, "no published source calls a padded county an error"
    finding = next(f for f in report.findings if f.rule_id == "QP024")
    assert finding.severity is Severity.WARNING
    assert "Contra Costa" in finding.message
    assert report.error_count == 0


@pytest.mark.parametrize("padded", ["01", "02", "03", "04", "05", "06", "07", "08", "09"])
def test_every_single_digit_county_is_recognised_when_padded(padded: str) -> None:
    data = _rows(PROFILE_1306A_S1, f"1,2025,1,{padded},B,A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert "QP013" not in _fired(report)
    assert "QP024" in _fired(report)


def test_the_unpadded_form_warns_about_nothing() -> None:
    data = _rows(PROFILE_1306A_S1, "1,2025,1,7,B,A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert report.findings == []


def test_unknown_county_double_zero_is_published_and_silent() -> None:
    """'00' is in the published table, so it is neither an error nor a warning."""
    data = _rows(PROFILE_1306A_S1, "1,2025,1,00,B,A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert report.findings == []


@pytest.mark.parametrize("value", ["007", "0007", "0", "077", "-24", "77"])
def test_over_padded_and_unknown_counties_are_still_errors(value: str) -> None:
    """Only the two-character padded form has published cover. Nothing else."""
    data = _rows(PROFILE_1306A_S1, f"1,2025,1,{value},B,A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    fired = _fired(report)
    assert "QP013" in fired
    assert "QP024" not in fired


def test_the_padding_table_covers_exactly_the_single_digit_counties() -> None:
    assert sorted(PADDED_COUNTY_NUMBERS) == [f"0{n}" for n in range(1, 10)]
    for padded, plain in PADDED_COUNTY_NUMBERS.items():
        assert plain in COUNTY_NUMBERS
        assert padded not in COUNTY_NUMBERS


# ---------------------------------------------------------------------------
# Customer Type, where two published CEC documents disagree
# ---------------------------------------------------------------------------


def test_customer_type_o_is_reported_for_attention_not_as_an_error() -> None:
    data = _rows(PROFILE_1306A_S1, "1,2025,1,34,O,A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    fired = _fired(report)

    assert "QP025" in fired
    assert "QP014" not in fired
    finding = next(f for f in report.findings if f.rule_id == "QP025")
    assert finding.severity is Severity.INFO
    assert "BART" in finding.message
    assert report.error_count == 0
    assert report.warning_count == 0


@pytest.mark.parametrize("value", ["D", "B", "C"])
def test_the_customer_types_in_the_instructions_are_silent(value: str) -> None:
    data = _rows(PROFILE_1306A_S1, f"1,2025,1,34,{value},A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert report.findings == []


def test_an_unpublished_customer_type_is_still_an_error() -> None:
    data = _rows(PROFILE_1306A_S1, "1,2025,1,34,X,A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    fired = _fired(report)

    assert "QP014" in fired
    assert "QP025" not in fired
    message = next(f.message for f in report.findings if f.rule_id == "QP014")
    # The filer is told about every value either published source allows.
    for allowed in ("B", "C", "D", "O"):
        assert allowed in message


def test_lowercase_customer_type_is_an_error() -> None:
    """The workshop deck says "uppercase letter", so case is not forgiven."""
    data = _rows(PROFILE_1306A_S1, "1,2025,1,34,o,A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert "QP014" in _fired(report)


def test_customer_group_is_case_sensitive() -> None:
    data = _rows(PROFILE_1306B, "1,2025,4,PGE,residential,1,1,1,1")
    report = validate_bytes(data, PROFILE_1306B, "x.csv")
    assert "QP015" in _fired(report)


def test_udc_must_be_one_of_three_values() -> None:
    data = _rows(PROFILE_1306B, "1,2025,4,PG&E,Residential,1,1,1,1")
    report = validate_bytes(data, PROFILE_1306B, "x.csv")
    assert "QP022" in _fired(report)


def test_gas_rate_code_must_be_published() -> None:
    data = _rows(PROFILE_1308B_S1, "1,2025,10,1,999999,15,1,1,1")
    report = validate_bytes(data, PROFILE_1308B_S1, "x.csv")
    assert "QP016" in _fired(report)


def test_teor_and_ueg_are_valid_gas_customer_groups() -> None:
    data = _rows(PROFILE_1308C, "1,2025,7,1,UEG,1,1,1")
    report = validate_bytes(data, PROFILE_1308C, "x.csv")
    assert "QP015" not in _fired(report)


def test_quarter_number_rule_on_schedule_2() -> None:
    profile = get_profile("CEC-1306A-S2")
    data = _rows(profile, "1,2025,5,A1,Some description")
    report = validate_bytes(data, profile, "x.csv")
    assert "QP012" in _fired(report)


def test_negative_values_are_not_rejected_as_non_numeric() -> None:
    """No published rule forbids a negative, so the tool must not invent one."""
    data = _rows(PROFILE_1306A_S1, "1,2025,1,1,B,A1,999999,1,-50,-12.34")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert "QP020" not in _fired(report)


def test_short_row_reports_field_count_not_field_errors() -> None:
    data = _rows(PROFILE_1306A_S1, "1,2025,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    fired = _fired(report)
    assert "QP003" in fired
    assert "QP013" not in fired


# ---------------------------------------------------------------------------
# Cross-row rules
# ---------------------------------------------------------------------------


def test_months_spanning_two_quarters_warn() -> None:
    data = _rows(
        PROFILE_1306A_S1,
        "1,2025,3,1,B,A1,999999,1,1,1",
        "1,2025,4,1,B,A1,999999,1,1,1",
    )
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert "QP030" in _fired(report)
    finding = next(f for f in report.findings if f.rule_id == "QP030")
    assert finding.severity is Severity.WARNING


def test_mixed_years_warn() -> None:
    data = _rows(
        PROFILE_1306A_S1,
        "1,2024,1,1,B,A1,999999,1,1,1",
        "1,2025,2,1,B,A1,999999,1,1,1",
    )
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert "QP031" in _fired(report)


def test_warnings_alone_do_not_make_it_a_failure() -> None:
    data = _rows(
        PROFILE_1306A_S1,
        "1,2025,3,1,B,A1,999999,1,1,1",
        "1,2025,4,1,B,A1,999999,1,1,1",
    )
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert report.error_count == 0
    assert report.warning_count >= 1


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def test_profile_lookup_is_case_insensitive() -> None:
    assert get_profile("cec-1306a-s1") is PROFILE_1306A_S1


def test_unknown_profile_raises() -> None:
    with pytest.raises(KeyError):
        get_profile("CEC-9999")


def test_every_profile_has_at_least_one_applicable_rule() -> None:
    for profile in PROFILES.values():
        assert specs_for(profile)


def test_bom_is_tolerated() -> None:
    data = b"\xef\xbb\xbf" + _rows(PROFILE_1306A_S1, "1,2025,1,1,B,A1,999999,1,1,1")
    report = validate_bytes(data, PROFILE_1306A_S1, "x.csv")
    assert "QP002" not in _fired(report)
