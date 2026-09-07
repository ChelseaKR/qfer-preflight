"""Profile detection from the file's header row.

Detection is a convenience with a fail-closed core: it matches the header
byte for byte against the transcribed templates and refuses to guess when the
match is zero or more than one. The refusal cases are as important as the
match case, because validating against the wrong form would produce findings
about columns that mean something else.

Detection reads the bytes of the first record and stops. That is a contract,
not a performance note, so it is tested directly: a defect past the header
belongs to the reader, which names the offending byte, and must never be
reported here as a fact about row one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qfer_preflight import detect
from qfer_preflight.cli import (
    EXIT_FINDINGS,
    EXIT_OK,
    EXIT_USAGE,
    main,
)

# The header scan moved to `detect` so the published Python API and the
# command line share one implementation. These tests follow it there; the
# behaviour they assert is unchanged.
from qfer_preflight.detect import read_header_bytes as _read_header_bytes
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


# A filing whose header is byte for byte correct and whose only defect is one
# invalid byte in a data row. The offsets bracket the 8 KB read-ahead window a
# text handle used to decode behind detection's back.
_HEADER = (",".join(PROFILES["CEC-1306A-S1"].header) + "\r\n").encode()
_GOOD_ROW = b"123,2025,3,14,B,RESIDENTIAL_OTHER,925190,10,1000.50,25\r\n"


def _filing_with_a_bad_byte_at(offset: int) -> bytes:
    """A valid filing with byte `offset` replaced by an invalid UTF-8 byte."""
    assert offset > len(_HEADER), "the point is a defect past the header"
    rows = _GOOD_ROW * (1 + (offset * 2) // len(_GOOD_ROW))
    payload = bytearray(_HEADER + rows)
    payload[offset] = 0xFF
    return bytes(payload)


@pytest.mark.parametrize("offset", [200, 4038, 8191, 8192, 8193, 9022, 12000])
def test_a_bad_byte_past_the_header_is_reported_the_same_wherever_it_falls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], offset: int
) -> None:
    """Regression: detection used to refuse or succeed depending on the offset.

    Reading the header through a text handle decoded a whole read-ahead block,
    so a `UnicodeDecodeError` raised by bytes far past the header landed in
    detection's handler and was reported as a fact about the first row. The
    filing then got no report at all. The identical defect a few thousand
    bytes later detected fine and got a report naming the offending byte.
    """
    path = _write(tmp_path, f"bad-at-{offset}.csv", _filing_with_a_bad_byte_at(offset))
    assert main(["check", path, "--format", "json"]) == EXIT_FINDINGS
    captured = capsys.readouterr()
    assert captured.err == ""

    report = json.loads(captured.out)
    assert report["profile"]["id"] == "CEC-1306A-S1"
    message = report["findings"][0]["message"]
    assert f"byte {offset} of the file is 0xFF" in message


@pytest.mark.parametrize("offset", [200, 9022])
def test_naming_the_profile_gives_the_same_answer_detection_now_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], offset: int
) -> None:
    """The two routes agreed already for a late byte and disagreed for an early one."""
    payload = _filing_with_a_bad_byte_at(offset)
    detected = _write(tmp_path, f"detected-{offset}.csv", payload)
    assert main(["check", detected, "--format", "json"]) == EXIT_FINDINGS
    by_detection = json.loads(capsys.readouterr().out)

    named = _write(tmp_path, f"named-{offset}.csv", payload)
    assert main(["check", named, "--format", "json", "--profile", "CEC-1306A-S1"]) == EXIT_FINDINGS
    by_name = json.loads(capsys.readouterr().out)

    del by_detection["input"]["name"], by_name["input"]["name"]
    assert by_detection == by_name


def test_a_bad_byte_past_the_header_does_not_take_a_batch_entry_down(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """In batch mode the false reason landed as the entry's `problem` instead."""
    early = _write(tmp_path, "early.csv", _filing_with_a_bad_byte_at(200))
    late = _write(tmp_path, "late.csv", _filing_with_a_bad_byte_at(9022))
    assert main(["check", early, late, "--format", "json"]) == EXIT_FINDINGS

    entries = json.loads(capsys.readouterr().out)["results"]
    assert [entry.get("problem") for entry in entries] == [None, None]
    assert [entry["report"]["findings"][0]["message"] for entry in entries] == [
        f"The file is not valid UTF-8 text: byte {n} of the file is 0xFF, which is "
        "not valid UTF-8. This tool reads UTF-8, so it could not open the file and "
        "validated nothing in it. Re-save the file as UTF-8 and run it again."
        for n in (200, 9022)
    ]


def test_detection_reads_the_header_row_and_no_more(tmp_path: Path) -> None:
    """The docstring's claim, made checkable.

    Nothing else in the suite could tell "reads the header" from "reads a
    block and stops at the header", which is what it was doing.
    """
    payload = _HEADER + _GOOD_ROW * 500
    assert len(payload) > 8192, "the fixture stopped reaching past the read-ahead window"
    path = _write(tmp_path, "big.csv", payload)
    assert _read_header_bytes(path) == _HEADER.rstrip(b"\r\n")


@pytest.mark.parametrize(
    "payload,expected",
    [
        (b"", b""),
        (b"\r\nrow\r\n", b""),
        (b"a,b", b"a,b"),
        (b"a,b\nrow", b"a,b"),
        (b"\xef\xbb\xbfa,b\r\nrow\r\n", b"\xef\xbb\xbfa,b"),
        (b'a,"line\r\nbreak",b\r\nrow\r\n', b'a,"line\r\nbreak",b'),
        (b'a,"a""b",c\r\nrow\r\n', b'a,"a""b",c'),
        (b'a,"unclosed\r\nrow', b'a,"unclosed\r\nrow'),
        (b'a,b"c\r\nrow', b'a,b"c'),
    ],
)
def test_the_record_scan_ends_where_csv_says_the_record_ends(
    tmp_path: Path, payload: bytes, expected: bytes
) -> None:
    """A line break inside a quoted field does not end the record; one outside does."""
    path = _write(tmp_path, "record.csv", payload)
    assert _read_header_bytes(path) == expected


def test_the_record_scan_agrees_with_csv_across_chunk_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scan carries quote state across reads, so the chunk size cannot matter."""
    payload = b'first,"quoted\r\nvalue",last\r\nsecond row\r\n'
    baseline = _read_header_bytes(_write(tmp_path, "baseline.csv", payload))
    path = _write(tmp_path, "chunked.csv", payload)
    for chunk in range(1, len(payload) + 2):
        monkeypatch.setattr(detect, "HEADER_CHUNK_BYTES", chunk)
        assert _read_header_bytes(path) == baseline, chunk
