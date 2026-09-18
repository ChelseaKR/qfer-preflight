"""SECURITY.md's "No retention" bullet, held to the code that writes files.

The bullet used to end *"Report output goes to stdout and nowhere else."* That
was true when it was written and stopped being true when `--findings-dir`
shipped: a batch findings run writes one table per input, and a findings table
quotes cell values out of the filing. Nothing failed, because nothing read the
sentence. A filer reading SECURITY.md to decide whether this tool may touch a
document eligible for confidential treatment was told no file could exist.

So the property is asserted twice, from two directions, because either one
alone rots the same way:

  * **Behaviourally.** A `check` run that names no destination writes nothing,
    anywhere: not into the working directory, not into the temporary
    directory. Every output format is exercised, because the writing one is
    the one a reader would assume is the exception.
  * **Structurally.** Every filesystem write in `src/` is enumerated, and the
    set of modules containing one is pinned. A write added anywhere else fails
    here, which is the moment to ask whether the bullet is still true.

The structural half also asserts the bullet names `--findings-dir`, so deleting
the flag's mention without deleting the flag fails too.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from qfer_preflight.cli import main

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "qfer_preflight"
SECURITY = ROOT / "SECURITY.md"
FIXTURES = Path(__file__).parent / "fixtures"

#: Ways this package could put bytes on disk. `open(...)` is matched only with
#: a writing mode, because the tool opens the filing itself for reading.
WRITE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("write_text", re.compile(r"\.write_text\(")),
    ("write_bytes", re.compile(r"\.write_bytes\(")),
    ("mkdir", re.compile(r"\.mkdir\(|os\.makedirs\(")),
    ("open-for-writing", re.compile(r"""open\([^)]*["'][wax]""")),
    ("tempfile", re.compile(r"\btempfile\.")),
    ("shutil-copy-or-move", re.compile(r"\bshutil\.(copy\w*|move)\(")),
    ("os-replace-or-rename", re.compile(r"\bos\.(replace|rename)\(")),
)

#: The one module allowed to write, and why. A second entry here is a change to
#: what SECURITY.md promises, not a refactor.
DECLARED_WRITERS: dict[str, str] = {
    "cli.py": "--findings-dir: one findings table per input, into a directory the caller names",
}


def _write_sites() -> dict[str, list[str]]:
    sites: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name, pattern in WRITE_PATTERNS:
                if pattern.search(line):
                    sites.setdefault(path.name, []).append(f"{path.name}:{number} {name}")
    return sites


def test_every_filesystem_write_in_the_package_is_declared() -> None:
    sites = _write_sites()
    assert sites, "found no write site at all: the patterns stopped matching, which is not a pass"
    assert set(sites) == set(DECLARED_WRITERS), (
        "a module writes to the filesystem that SECURITY.md's no-retention bullet does not "
        f"account for: {sorted(set(sites) ^ set(DECLARED_WRITERS))}; sites={sites}"
    )


def test_the_no_retention_bullet_names_the_flag_that_writes() -> None:
    text = SECURITY.read_text(encoding="utf-8")
    start = text.index("- **No retention.**")
    bullet = text[start : text.index("\n- **", start + 1)]
    assert "--findings-dir" in bullet, (
        "the no-retention bullet does not name --findings-dir, the one option that makes "
        f"this tool write a file:\n{bullet}"
    )
    assert "stdout and nowhere else" not in text, (
        "SECURITY.md still says report output goes to stdout and nowhere else; "
        "--findings-dir writes findings tables, and they quote cell values"
    )


@pytest.mark.parametrize("fmt", ["text", "json", "sarif", "findings-csv", "findings-jsonl"])
def test_a_check_that_names_no_destination_writes_no_file(
    fmt: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every format, one dirty input, nothing on disk afterwards.

    The working directory and the temporary directory are both scratch trees
    created here, so a stray write lands somewhere this test can see. Both are
    listed before and after and compared as sets of paths.
    """
    work = tmp_path / "work"
    temp = tmp_path / "temp"
    work.mkdir()
    temp.mkdir()
    monkeypatch.chdir(work)
    for variable in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(variable, str(temp))

    before = {p for root in (work, temp) for p in root.rglob("*")}
    main(["check", str(FIXTURES / "1306a_s1_dirty.csv"), "--format", fmt])
    captured = capsys.readouterr()
    after = {p for root in (work, temp) for p in root.rglob("*")}

    assert captured.out, f"--format {fmt} wrote nothing to stdout, so this proves nothing"
    assert after == before, f"--format {fmt} wrote {sorted(str(p) for p in after - before)}"


def test_the_findings_dir_flag_really_does_write(tmp_path: Path) -> None:
    """The other direction: the exception the bullet now names is real.

    Without this, deleting `--findings-dir` would leave the two tests above
    green and the bullet describing a flag that no longer exists.
    """
    out = tmp_path / "tables"
    main(
        [
            "check",
            str(FIXTURES / "1306a_s1_dirty.csv"),
            str(FIXTURES / "1306a_s1_clean.csv"),
            "--format",
            "findings-csv",
            "--findings-dir",
            str(out),
        ]
    )
    written = sorted(p.name for p in out.glob("*.findings.csv"))
    assert written == ["1306a_s1_clean.findings.csv", "1306a_s1_dirty.findings.csv"], written
    dirty = (out / "1306a_s1_dirty.findings.csv").read_text(encoding="utf-8")
    assert "cell" in dirty and "QP010" in dirty, dirty[:400]
