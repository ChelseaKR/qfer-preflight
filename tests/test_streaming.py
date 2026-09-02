"""The bounded-memory reader agrees with the whole-text definitions it replaced.

`validate_path` no longer holds the filing in memory: it walks the bytes once
in chunks, keeping facts instead of content, then streams rows off disk. Every
fact it collects mirrors a definition once written against the whole text, so
these tests hold each scanner against its reference:

  * `_QuoteTrail` versus `_unterminated_quote`, the reference definition of
    truncation, across generated strings and forced chunk boundaries;
  * the line-ending counters versus counting the whole text directly;
  * end-to-end report equality between `validate_path` and `validate_bytes`
    for every fixture, a multi-chunk synthetic filing, and hostile inputs,
    with the chunk size shrunk until boundaries land inside multibyte
    characters, escaped quotes and carriage returns.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from qfer_preflight import engine
from qfer_preflight.engine import (
    _QuoteTrail,
    _StreamScan,
    _unterminated_quote,
    validate_bytes,
    validate_path,
)
from qfer_preflight.profiles import PROFILES, get_profile
from qfer_preflight.report import to_json

FIXTURES = Path(__file__).parent / "fixtures"

HOSTILE_PAYLOADS = [
    b"",
    b"   \n  \n",
    b"\xef\xbb\xbf",
    b"\xef\xbb\xbf   \r\n \t ",
    b"\xc2\xa0",
    b" \xc2\xa0\xc2\xa0 ",
    b"\xff\xfe\x00\x00not utf-8 at all \xc3\x28",
    b"\xef\xbb\xbfCompanyNumber,Year,\xff",
    b"\xef\xbb\xbfab\xc3",  # cut in half at the very end
    b"abc\xe2\x80",  # flush error: character split by EOF
    b'CompanyNumber,Year\r\n123,"2025',  # truncated inside a quoted value
    b'CompanyNumber,Year\r\n123,"2025"\r\n',  # the same, complete
    b'x,y\r\n"a""b",2\r\n',  # escaped quotes inside a field
    b'x,y\r\n"a"",2\r\n',  # quote, escape, open again, never closed
    b"a,b\rc,d\n",  # mixed line endings
    b"a\r\nb\nc\r",  # CR at EOF, after CRLF and LF
]


def _report_bytes(payload: bytes, name: str = "x.csv") -> str:
    return to_json(validate_bytes(payload, get_profile("CEC-1306A-S1"), name))


def _report_file(path: Path) -> str:
    return to_json(validate_path(str(path), get_profile("CEC-1306A-S1")))


def _write(tmp_path: Path, name: str, payload: bytes) -> Path:
    target = tmp_path / name
    target.write_bytes(payload)
    return target


def _assert_same_report(tmp_path: Path, payload: bytes, name: str) -> None:
    """Same bytes through both entrances must render identical reports."""
    path = _write(tmp_path, name, payload)
    assert _report_file(path) == _report_bytes(payload, name), name


def test_every_fixture_produces_the_same_report_from_disk_and_memory(
    tmp_path: Path,
) -> None:
    for fixture in sorted(FIXTURES.glob("*.csv")):
        _assert_same_report(tmp_path, fixture.read_bytes(), fixture.name)


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 4, 7, 13])
def test_hostile_payloads_survive_every_chunk_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chunk_size: int
) -> None:
    monkeypatch.setattr(engine, "_CHUNK_BYTES", chunk_size)
    for i, payload in enumerate(HOSTILE_PAYLOADS):
        _assert_same_report(tmp_path, payload, f"hostile-{i}.csv")


def test_a_multi_chunk_filing_matches_its_in_memory_twin(tmp_path: Path) -> None:
    header = ",".join(PROFILES["CEC-1306A-S1"].header)
    row = '123,2025,3,14,B,"RESIDENTIAL_OTHER",925190,10,1000.50,25'
    body = "\r\n".join([header, *[row] * 20_000, ""])
    payload = body.encode("utf-8")
    assert len(payload) > 1 << 20, "the fixture stopped crossing a chunk boundary"
    _assert_same_report(tmp_path, payload, "big.csv")


def test_multibyte_characters_straddling_the_boundary_are_read_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    header = ",".join(PROFILES["CEC-1306A-S2"].header)
    profile = get_profile("CEC-1306A-S2")
    payload = (header + "\r\n").encode("utf-8") + "123,2025,1,Résidentiel,dé".encode()

    monkeypatch.setattr(engine, "_CHUNK_BYTES", 5)
    by_chunk = to_json(validate_bytes(payload, profile, "s2.csv"))
    monkeypatch.setattr(engine, "_CHUNK_BYTES", 1 << 20)
    whole = to_json(validate_bytes(payload, profile, "s2.csv"))
    assert by_chunk == whole


def test_quote_trail_agrees_with_the_reference_on_generated_strings() -> None:
    rng = random.Random(20260823)
    alphabet = 'a,"\r\n ,xé'
    for _trial in range(2000):
        length = rng.randrange(0, 24)
        text = "".join(rng.choice(alphabet) for _ in range(length))

        trail = _QuoteTrail()
        # Feed it in ragged slices so boundaries land everywhere.
        position = 0
        while position < len(text):
            take = rng.randrange(1, 5)
            trail.feed(text[position : position + take])
            position += take
        assert trail.finish() is _unterminated_quote(text), repr(text)


def test_stream_scan_counts_match_counting_the_whole_text() -> None:
    rng = random.Random(42)
    alphabet = 'a,"\r\n \t'
    for _trial in range(500):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 40)))
        scan = _StreamScan()
        position = 0
        while position < len(text):
            take = rng.randrange(1, 6)
            scan.feed(text[position : position + take].encode("utf-8"))
            position += take
        scan.finish()
        ingest = scan.result()

        crlf = text.count("\r\n")
        lf = text.count("\n") - crlf
        cr = text.count("\r") - crlf
        assert (ingest.crlf, ingest.lf, ingest.cr) == (crlf, lf, cr), repr(text)
        assert ingest.has_content is bool(text.strip()), repr(text)


def test_decode_error_names_the_exact_byte_after_a_bom(tmp_path: Path) -> None:
    """Regression: offsets count physical file bytes, mark included."""
    payload = b"\xef\xbb\xbfabc,\xff"
    report = json.loads(_report_bytes(payload))
    finding = report["findings"][0]["message"]
    assert "byte 7 of the file is 0xFF" in finding
    _assert_same_report(tmp_path, payload, "bom-invalid.csv")


def test_a_character_cut_in_half_by_eof_is_named_by_its_first_byte() -> None:
    payload = b"abc\xe2\x80"
    report = json.loads(_report_bytes(payload))
    assert "byte 3 of the file is 0xE2" in report["findings"][0]["message"]


def test_each_kind_of_nothing_says_which_it_is(tmp_path: Path) -> None:
    cases = {
        b"": "no bytes in it at all",
        b"\xef\xbb\xbf": "nothing but a UTF-8 byte order mark, the bytes EF BB BF",
        b"\xef\xbb\xbf \r\n\t ": "byte order mark and whitespace",
        b" \t\r\n ": "5 bytes of whitespace",
        b"\xc2\xa0": "2 bytes of whitespace",
    }
    for i, (payload, expected) in enumerate(cases.items()):
        report = json.loads(_report_bytes(payload))
        assert expected in report["findings"][0]["message"], payload
        _assert_same_report(tmp_path, payload, f"nothing-{i}.csv")


def test_no_message_leaves_a_space_in_front_of_its_punctuation(tmp_path: Path) -> None:
    """A hole left by an interpolation that went away is still visible.

    The byte order mark case read "byte order mark , the bytes EF BB BF" for
    the life of the streaming reader, because an optional `{tail}` was removed
    and the space in front of it stayed. This walks every message the reader
    can produce for a file it refuses, rather than pinning the one that was
    wrong, since the next such hole will be somewhere else.
    """
    payloads = [
        b"",
        b"\xef\xbb\xbf",
        b"\xef\xbb\xbf \r\n\t ",
        b" \t\r\n ",
        b"\xc2\xa0",
        b"abc\xff",
        b'CompanyNumber,Year\r\n123,"open',
    ]
    for payload in payloads:
        report = json.loads(_report_bytes(payload))
        messages = [f["message"] for f in report["findings"]]
        messages += [a["message"] for a in report["advisories"]]
        assert messages, payload
        for message in messages:
            for punctuation in (" ,", " .", " ;", " :", "  "):
                assert punctuation not in message, (payload, punctuation, message)


def test_truncation_detected_when_the_open_quote_crosses_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"CompanyNumber,Ye"
    monkeypatch.setattr(engine, "_CHUNK_BYTES", 4)
    # Not a real header, but QP001 gating means the report must still agree
    # between the two entrances whatever the header says.
    _assert_same_report(tmp_path, payload + b'ar\r\n123,"open', "truncated.csv")


def test_sha256_matches_hashing_the_whole_file(tmp_path: Path) -> None:
    import hashlib

    payload = HOSTILE_PAYLOADS[10] + b"more bytes, same file"
    path = _write(tmp_path, "hashed.csv", payload)
    report = json.loads(_report_file(path))
    assert report["input"]["sha256"] == hashlib.sha256(payload).hexdigest()
