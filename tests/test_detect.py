"""Profile detection from the file's header row.

Detection is a convenience with a fail-closed core: it matches the header
byte for byte against the transcribed templates and refuses to guess when the
match is zero or more than one. The refusal cases are as important as the
match case, because validating against the wrong form would produce findings
about columns that mean something else.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qfer_preflight.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main
from qfer_preflight.profiles import (
    PROFILES,
    Profile,
    detect_profiles,
    get_profile,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_detection_matches_the_published_header_exactly() -> None:
    profile = get_profile("CEC-1306A-S1")
    assert detect_profiles(profile.header) == (profile,)


def test_detection_is_exact_against_every_template() -> None:
    for profile in PROFILES.values():
        assert detect_profiles(profile.header) == (profile,), profile.id


def test_detection_refuses_a_reordered_or_edited_header() -> None:
    header = list(PROFILES["CEC-1306B"].header)
    reordered = [header[1], header[0], *header[2:]]
    assert detect_profiles(reordered) == ()
    edited = [*header[:-1], header[-1] + " "]
    assert detect_profiles(edited) == ()


def test_detection_reports_ambiguity_rather_than_guessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two templates with one header must both come back, so callers refuse.

    No two published templates collide today. This guards the day one does:
    the function must surface the collision, not silently pick a winner.
    """
    original = PROFILES["CEC-1306B"]
    twin = Profile(
        id="CEC-TWIN",
        title=original.title,
        authority=original.authority,
        instructions_url=original.instructions_url,
        instructions_name=original.instructions_name,
        template_url=original.template_url,
        header=original.header,
    )
    monkeypatch.setattr(
        "qfer_preflight.profiles.PROFILES",
        {"CEC-1306B": original, "CEC-TWIN": twin},
    )
    matched = detect_profiles(original.header)
    assert {p.id for p in matched} == {"CEC-1306B", "CEC-TWIN"}


def _write(tmp_path: Path, name: str, payload: bytes) -> str:
    target = tmp_path / name
    target.write_bytes(payload)
    return str(target)


def test_cli_detects_each_profile_from_its_clean_fixture(
    capsys: pytest.CaptureFixture[str],
) -> None:
    detected = {
        "1306a_s1_clean.csv": "CEC-1306A-S1",
        "1306b_clean.csv": "CEC-1306B",
        "1308b_s1_clean.csv": "CEC-1308B-S1",
        "1308c_clean.csv": "CEC-1308C",
    }
    for fixture, expected_id in detected.items():
        code = main(["check", str(FIXTURES / fixture), "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert code == EXIT_OK
        assert payload["profile"]["id"] == expected_id


def test_cli_detects_schedule_2_from_a_written_header(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = get_profile("CEC-1306A-S2")
    path = _write(tmp_path, "s2.csv", (",".join(profile.header) + "\r\n").encode())
    assert main(["check", path, "--format", "json"]) == EXIT_FINDINGS  # no data rows
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"]["id"] == "CEC-1306A-S2"


def test_cli_refuses_to_guess_on_a_header_it_does_not_recognise(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "wrong.csv", b"CompanyNumber,Year\r\n123,2025\r\n")
    assert main(["check", path]) == EXIT_USAGE
    err = capsys.readouterr().err
    assert "does not match any published template" in err


def test_cli_refuses_an_empty_file_without_a_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "empty.csv", b"")
    assert main(["check", path]) == EXIT_USAGE
    assert "no rows" in capsys.readouterr().err


def test_cli_refuses_bytes_it_cannot_read_as_utf8(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "binary.csv", b"\xff\xfe\x00\x00not utf-8 \xc3\x28")
    assert main(["check", path]) == EXIT_USAGE
    err = capsys.readouterr().err
    assert "--profile explicitly" in err


def test_cli_still_validates_when_the_profile_is_named_despite_a_bad_header(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Naming the profile skips detection; validation reports the bad header."""
    code = main(["check", str(FIXTURES / "wrong_header.csv"), "--profile", "CEC-1306A-S1"])
    assert code == EXIT_FINDINGS
    capsys.readouterr()


def test_explicit_unknown_profile_still_exits_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["check", str(FIXTURES / "empty.csv"), "--profile", "NOPE"]) == EXIT_USAGE
    capsys.readouterr()
