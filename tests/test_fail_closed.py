"""The defining property: what cannot be measured is never reported as clean.

These tests are the reason the project exists. If any of them starts failing,
the tool has begun telling filers that unchecked documents are fine, which is
worse than not having the tool at all.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from qfer_preflight.engine import validate_bytes, validate_path
from qfer_preflight.model import Status
from qfer_preflight.profiles import PROFILE_1306A_S1, get_profile
from qfer_preflight.report import to_json

FIXTURES = Path(__file__).parent / "fixtures"


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _report_json(name: str, profile_id: str = "CEC-1306A-S1") -> str:
    return to_json(validate_path(str(FIXTURES / name), get_profile(profile_id)))


def test_empty_input_does_not_hash_to_the_same_report_as_a_clean_one() -> None:
    """An empty file must not produce the output a clean file produces."""
    clean = _report_json("1306a_s1_clean.csv")
    empty = _report_json("empty.csv")

    assert _digest(clean) != _digest(empty), (
        "an empty submission produced the same report as a clean one, which "
        "means the tool cannot distinguish unchecked from checked"
    )


def test_malformed_input_does_not_hash_to_the_same_report_as_a_clean_one() -> None:
    """A file with the wrong header must not look like a clean file either."""
    clean = _report_json("1306a_s1_clean.csv")
    malformed = _report_json("wrong_header.csv")

    assert _digest(clean) != _digest(malformed)


def test_all_three_inputs_hash_differently() -> None:
    """Clean, empty and malformed are three distinct outcomes, not two."""
    digests = {
        "clean": _digest(_report_json("1306a_s1_clean.csv")),
        "empty": _digest(_report_json("empty.csv")),
        "malformed": _digest(_report_json("wrong_header.csv")),
    }
    assert len(set(digests.values())) == 3, digests


def test_empty_input_is_never_a_pass() -> None:
    report = validate_bytes(b"", PROFILE_1306A_S1, "empty.csv")
    assert report.status is Status.FAIL
    assert report.error_count >= 1


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"   \n  \n",
        b"\xff\xfe\x00\x00not utf-8 at all \xc3\x28",
    ],
)
def test_unreadable_inputs_report_an_error_and_evaluate_nothing_else(
    payload: bytes,
) -> None:
    report = validate_bytes(payload, PROFILE_1306A_S1, "x.csv")
    assert report.status is Status.FAIL
    assert "QP001" in {f.rule_id for f in report.findings}
    # Every other rule must be listed as unevaluated, never silently passed.
    assert report.rules_evaluated == ["QP001"]
    assert len(report.rules_not_evaluated) > 5


def test_header_mismatch_leaves_column_rules_unevaluated() -> None:
    report = validate_path(str(FIXTURES / "wrong_header.csv"), PROFILE_1306A_S1)
    unevaluated = {n.rule_id for n in report.rules_not_evaluated}

    assert report.status is Status.FAIL
    assert "QP002" in {f.rule_id for f in report.findings}
    # None of the column-dependent rules may claim to have run.
    for rule_id in ("QP010", "QP011", "QP013", "QP014", "QP017", "QP019", "QP020"):
        assert rule_id in unevaluated, f"{rule_id} must not be reported as evaluated"
        assert rule_id not in report.rules_evaluated


def test_a_header_only_file_is_not_a_pass() -> None:
    """A file with a correct header and no rows has validated nothing."""
    header = ",".join(PROFILE_1306A_S1.header).encode() + b"\r\n"
    report = validate_bytes(header, PROFILE_1306A_S1, "header_only.csv")

    assert report.status is Status.FAIL
    assert "QP006" in {f.rule_id for f in report.findings}
    assert report.rows_read == 0


def test_unimplemented_rules_are_always_reported_as_unevaluated() -> None:
    """Even a spotless file must disclose what was not checked."""
    report = validate_path(str(FIXTURES / "1306a_s1_clean.csv"), PROFILE_1306A_S1)
    unevaluated = {n.rule_id for n in report.rules_not_evaluated}

    assert "QP018" in unevaluated, "the NAICS list rule has no published list to check"
    assert "QP005" in unevaluated, "totals-row detection has no deterministic test"
    assert "QP032" in unevaluated, "duplicate detection has no published key"


def test_a_clean_file_is_reported_unvalidated_not_pass() -> None:
    """The tool has no way to say 'clean' while rules remain unevaluated.

    This is intentional. Every profile registers at least one rule that is
    published but not mechanically checkable, so the honest verdict for a
    file with no findings is 'unvalidated', not 'pass'.
    """
    report = validate_path(str(FIXTURES / "1306a_s1_clean.csv"), PROFILE_1306A_S1)

    assert report.error_count == 0
    assert report.status is Status.UNVALIDATED


def test_every_unevaluated_rule_states_a_reason() -> None:
    report = validate_path(str(FIXTURES / "empty.csv"), PROFILE_1306A_S1)
    for item in report.rules_not_evaluated:
        assert item.reason.strip(), f"{item.rule_id} was skipped without saying why"


def test_report_json_is_deterministic() -> None:
    """Same bytes in, byte-identical report out."""
    first = _report_json("1306a_s1_clean.csv")
    second = _report_json("1306a_s1_clean.csv")
    assert first == second
