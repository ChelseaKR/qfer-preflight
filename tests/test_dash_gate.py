"""The dash gate must be able to fail.

`CLAUDE.md` states that em dashes and en dashes appear nowhere in this
repository and that `make verify` enforces it. For the whole life of the
repository it did not. The `no-dashes` target searched for

    git grep -n -P '\\xe2\\x80\\x93|\\xe2\\x80\\x94'

which reads as bytes but is not. In a PCRE pattern `\\xe2` is the single
codepoint U+00E2 (a with circumflex), not the first byte of a UTF-8 en dash,
so the alternation asked for two three-character sequences that no ordinary
text contains. The target printed "no em/en dashes" on every run, including
runs where a tracked file held a real en dash, which `.pre-commit-config.yaml`
did.

That is the failure mode this project is most exposed to: a check that is
present, green, and incapable of reporting the thing it exists to report. So
the pattern is asserted here against real dash characters rather than trusted
to be read correctly by eye.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"

EN_DASH = "\u2013"
EM_DASH = "\u2014"

_PATTERN = re.compile(r"git grep -n -P '([^']+)'")


def _gate_pattern() -> str:
    """The PCRE the `no-dashes` target actually searches with."""
    text = MAKEFILE.read_text(encoding="utf-8")
    match = _PATTERN.search(text)
    assert match, "the no-dashes target no longer runs `git grep -n -P '...'`"
    return match.group(1)


def _matches(pattern: str, content: str, tmp_path: Path) -> bool:
    """True when the gate's own matcher finds `pattern` in `content`.

    Deliberately `git grep`, not `grep`. The gate runs `git grep -P`, and the
    two are not interchangeable: BSD grep, which is `/usr/bin/grep` on macOS,
    has no `-P` at all, so a test written against `grep` would report the gate
    broken on a developer machine and working in CI. `--no-index` lets the
    same matcher run over a scratch file outside any repository.
    """
    probe = tmp_path / "probe.txt"
    probe.write_text(content, encoding="utf-8")
    completed = subprocess.run(
        ["git", "grep", "--no-index", "-c", "-P", pattern, "--", "probe.txt"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def test_the_gate_pattern_matches_a_real_en_dash(tmp_path: Path) -> None:
    assert _matches(_gate_pattern(), f"before {EN_DASH} after\n", tmp_path), (
        "the no-dashes pattern does not match an en dash, so the gate cannot fail"
    )


def test_the_gate_pattern_matches_a_real_em_dash(tmp_path: Path) -> None:
    assert _matches(_gate_pattern(), f"before {EM_DASH} after\n", tmp_path), (
        "the no-dashes pattern does not match an em dash, so the gate cannot fail"
    )


def test_the_gate_pattern_leaves_ordinary_text_alone(tmp_path: Path) -> None:
    """A gate that matches everything is as useless as one that matches nothing."""
    ordinary = "a hyphen - and a minus sign, plain ASCII, nothing typographic\n"
    assert not _matches(_gate_pattern(), ordinary, tmp_path)


def test_the_byte_escape_form_is_not_reintroduced() -> None:
    """The exact spelling that made this gate dead for the repository's whole life."""
    pattern = _gate_pattern()
    assert "\\xe2" not in pattern, (
        "\\xe2 in a PCRE is codepoint U+00E2, not a UTF-8 lead byte. That "
        "spelling matches no dash and made `make no-dashes` vacuous. Use the "
        "codepoint form \\x{2013} and \\x{2014}"
    )


def test_the_repository_itself_is_clean() -> None:
    """What the gate is for, asserted directly rather than through the gate."""
    completed = subprocess.run(
        ["git", "grep", "-n", "-P", f"{EN_DASH}|{EM_DASH}", "--", ":!*.lock", ":!uv.lock"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0, f"em/en dashes in tracked files:\n{completed.stdout}"
