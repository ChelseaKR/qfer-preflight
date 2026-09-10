"""A written findings table must carry the line endings its renderer chose.

`findings_table.py` pins its terminator twice and deliberately: the CSV writer is
constructed with `lineterminator="\\n"`, and the JSONL renderer joins on `"\\n"`.
`cli.py` then wrote the result with `Path.write_text(text, encoding="utf-8")`, which
opens the handle with `newline=None` -- text mode with translation **on**. Python
then rewrites every `\\n` as `os.linesep`, so the same command over the same filing
emitted `\\n` on Linux and `\\r\\n` on Windows.

Two things make that worth a module of its own rather than a one-word fix.

**It is invisible from the platform CI runs on.** `os.linesep` is `"\\n"` on Linux and
macOS, so the translation is the identity there and no assertion about the written
bytes could ever have failed. The defect lived on the one platform the matrix did not
cover, which is also the platform this tool's own roadmap names as the reason to want
a matrix: filers produce these files in Excel on Windows.

**It defeats a decision made two layers down.** `--findings-bom` exists so a filer can
control the exact bytes Excel receives. A flag at that level of precision sitting on
top of output whose line endings the tool had stopped choosing is the kind of
disagreement between a module and its caller that no single reading finds.

So there are two tests here and they are different in kind. The first compares what
reached disk with what the renderer produced: it is the real gate, it is what the
Windows leg exercises, and on a POSIX machine it passes whether or not the fix is
present -- stated here rather than left for a reader to discover. The second holds
the writer to the property directly, against a control handle that really does
translate, and that one discriminates on every platform.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from qfer_preflight.findings_table import write_table

FIXTURES = Path(__file__).parent / "fixtures"

#: What a translating text handle does to a newline on Windows, written out so the
#: control below is the same on every platform instead of being whatever the machine
#: running it happens to do.
WINDOWS_LINESEP = "\r\n"


def _write_through_a_translating_handle(path: Path, text: str) -> None:
    """Write `text` the way `Path.write_text` writes it on Windows.

    `newline=None` on a write handle means "translate `\\n` to `os.linesep`", so on
    Linux it is the identity and cannot stand in for the Windows behaviour. Naming
    the terminator explicitly reproduces that behaviour everywhere, which is what
    lets the assertion below discriminate on the machine this suite usually runs on.
    """
    with open(path, "w", encoding="utf-8", newline=WINDOWS_LINESEP) as handle:
        handle.write(text)


# ---------------------------------------------------------------------------
# The writer, held to the property directly. Discriminates on every platform.
# ---------------------------------------------------------------------------


def test_the_writer_does_not_translate_the_line_endings_it_was_given(tmp_path: Path) -> None:
    """What `write_table` puts on disk is what it was handed, byte for byte."""
    text = "# header\r\nrow,one\nrow,two\n"
    ours = tmp_path / "ours.csv"
    write_table(ours, text)
    assert ours.read_bytes() == text.encode("utf-8"), (
        "write_table changed the bytes of the table on the way to disk; the "
        "renderer's line-terminator choice is no longer what a reader receives"
    )


def test_a_translating_handle_really_would_have_changed_those_bytes(tmp_path: Path) -> None:
    """The control, so the test above is not passing because nothing was at stake.

    Without this, `write_table` writing bytes unchanged is indistinguishable from a
    platform on which no writer would have changed them. This proves the hazard is
    real by reproducing it, on whatever machine the suite is running.
    """
    text = "row,one\nrow,two\n"
    translated = tmp_path / "translated.csv"
    _write_through_a_translating_handle(translated, text)
    assert translated.read_bytes() != text.encode("utf-8"), (
        "the control handle did not translate anything, so it cannot show that "
        "write_table is doing something a plain text handle would not"
    )
    assert translated.read_bytes() == text.replace("\n", WINDOWS_LINESEP).encode("utf-8")


def test_the_writer_and_the_translating_handle_disagree(tmp_path: Path) -> None:
    """The two paths differ on the same input, which is the whole finding."""
    text = "row,one\nrow,two\n"
    ours, theirs = tmp_path / "a.csv", tmp_path / "b.csv"
    write_table(ours, text)
    _write_through_a_translating_handle(theirs, text)
    assert ours.read_bytes() != theirs.read_bytes(), (
        "write_table now produces the same bytes as a translating handle, so it "
        "has stopped defending the renderer's terminator"
    )


def test_the_writer_is_what_the_command_line_uses() -> None:
    """A seam nothing calls defends nothing.

    `write_table` exists so there is one place a rendered table reaches a file. If
    `cli.py` goes back to calling `write_text` directly, the tests above keep passing
    over a function no shipped path runs -- the shape this repository audits for.
    """
    source = (Path(__file__).resolve().parents[1] / "src" / "qfer_preflight" / "cli.py").read_text(
        encoding="utf-8"
    )
    assert "write_table(" in source, "cli.py no longer writes findings tables through write_table"
    assert "destination.write_text(" not in source, (
        "cli.py writes a findings table with write_text again, which translates "
        "line endings on Windows"
    )


# ---------------------------------------------------------------------------
# End to end. The real gate; vacuous on POSIX and load-bearing on Windows.
# ---------------------------------------------------------------------------


def _cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "qfer_preflight", *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("fmt,suffix", [("findings-csv", "csv"), ("findings-jsonl", "jsonl")])
def test_a_written_table_carries_only_the_terminator_the_renderer_chose(
    tmp_path: Path, fmt: str, suffix: str
) -> None:
    """No `\\r\\n` reaches disk, whichever machine ran the command.

    On Linux and macOS `os.linesep` is `"\\n"`, so this assertion held before the
    fix as well: it is the Windows leg of the CI matrix that gives it teeth. Said
    plainly because a green run here is not evidence the translation is handled --
    only a green run on Windows is.

    Two inputs, because `--findings-dir` is the batch path and a single input
    renders to stdout. The written file is the only surface where the platform
    gets to rewrite anything, so it is the only one worth asserting over.
    """
    out = tmp_path / "tables"
    result = _cli(
        [
            "check",
            str(FIXTURES / "1306a_s1_dirty.csv"),
            str(FIXTURES / "1306a_s1_clean.csv"),
            "--format",
            fmt,
            "--findings-dir",
            str(out),
        ]
    )
    assert result.returncode in (0, 1), result.stderr
    written = sorted(out.glob(f"*.findings.{suffix}"))
    assert written, (
        f"no findings table was written, so this check examined nothing: {result.stderr}"
    )
    for path in written:
        raw = path.read_bytes()
        assert b"\r\n" not in raw, (
            f"{path.name} carries CRLF; the renderer pinned LF and the write path "
            f"translated it (os.linesep is {os.linesep!r} here)"
        )
