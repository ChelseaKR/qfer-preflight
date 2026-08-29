"""Digit classes are written `[0-9]`, and the rule is enforced rather than remembered.

`CLAUDE.md` states it as a hard guardrail, and states why: Python's `\\d`
matches every Unicode decimal digit, and `int()` converts them all. `\\d{4}`
accepts the fullwidth "2025" and `\\d{1,2}` accepts the Arabic-Indic "5", so a
Year and a Month no portal would take once passed with no finding at all.

Nothing enforced it. When this file was written, `engine.py` held four digit
regexes. Rewriting three of them to `\\d` turned the suite red, because the
adversarial corpus carries a fullwidth or Arabic-Indic case for each. Rewriting
the fourth, `_COMPANY_NUMBER_DIGITS`, left the suite entirely green: QP033
would have accepted a Company Number in fullwidth digits and said nothing. That
case now exists, but it had to be noticed first, and the next regex to arrive
would have the same problem.

So the convention is checked at the source instead of one input at a time.

The check reads the AST rather than grepping, for a reason the alternative
makes obvious: every occurrence of `\\d` in this repository today sits in prose
explaining why not to use it, including three lines of `engine.py` and two of
this file's own siblings. A text search would either flag all of them or be
written loosely enough to miss a real one. Only the strings that actually reach
`re` are regexes, so only those are examined.

Written the way `test_dash_gate.py` is written: the matcher is asserted against
a pattern that must be caught and a pattern that must not, rather than trusted
to be read correctly by eye. A gate nobody has watched fail is not a gate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Functions that take a regular expression as their first argument.
_RE_FUNCTIONS = frozenset(
    {
        "compile",
        "match",
        "search",
        "fullmatch",
        "sub",
        "subn",
        "split",
        "findall",
        "finditer",
    }
)

# `\d` and its complement. Both are the Unicode-wide digit class this project
# refuses; `\D` is "not one of those", which is the same breadth inverted and
# would be the same silent hole.
_FORBIDDEN = ("\\d", "\\D")


def _python_files() -> list[Path]:
    """Every Python file in the project's own source, tests and scripts."""
    found = sorted(
        path
        for directory in ("src", "tests", "scripts")
        for path in (ROOT / directory).rglob("*.py")
    )
    assert found, "found no Python files to check, so this gate would pass vacuously"
    return found


def _regex_literals(source: str) -> list[tuple[int, str]]:
    """Every string literal this module hands to `re` as a pattern.

    Returns (line number, pattern) pairs. Only the first argument of a call to
    a function named like an `re` entry point is treated as a pattern, so a
    docstring or a comment mentioning a pattern is never examined.
    """
    tree = ast.parse(source)
    patterns: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name not in _RE_FUNCTIONS:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            patterns.append((first.lineno, first.value))
    return patterns


def _offenders(source: str) -> list[tuple[int, str]]:
    """The (line, pattern) pairs that break the convention."""
    return [
        (lineno, pattern)
        for lineno, pattern in _regex_literals(source)
        if any(token in pattern for token in _FORBIDDEN)
    ]


# ---------------------------------------------------------------------------
# The matcher must be able to fail, and must not fire on the right spelling
# ---------------------------------------------------------------------------


def test_the_check_catches_a_unicode_digit_class() -> None:
    planted = 're.compile(r"^\\d{4}$")'
    assert _offenders(planted), (
        "the check does not flag a regex written with a Unicode digit class, "
        "so it cannot enforce the convention it exists for"
    )


def test_the_check_catches_the_escaped_spelling_too() -> None:
    """`"\\\\d"` in a plain string is the same pattern as `r"\\d"`."""
    planted = 're.compile("^\\\\d{4}$")'
    assert _offenders(planted)


def test_the_check_catches_the_negated_class() -> None:
    assert _offenders('re.compile(r"[\\D]+")')


def test_the_check_leaves_the_published_spelling_alone() -> None:
    """A gate that flags everything is as useless as one that flags nothing."""
    correct = 're.compile(r"^[0-9]{4}$")\nre.fullmatch(r"^[+-]?[0-9]+$", value)'
    assert not _offenders(correct)


def test_the_check_ignores_prose_that_merely_mentions_the_class() -> None:
    """The reason this reads the AST: the repository discusses `\\d` constantly."""
    prose = '# never write \\d here\nX = "a \\\\d in a plain string"\nre.compile(r"[0-9]")'
    assert not _offenders(prose)


def test_the_check_reads_more_than_re_compile() -> None:
    """`re.fullmatch(pattern, value)` is just as much a regex as `re.compile`."""
    assert _offenders('re.fullmatch(r"\\d+", value)')
    assert _offenders('re.sub(r"\\d", "", value)')


# ---------------------------------------------------------------------------
# What the gate is for
# ---------------------------------------------------------------------------


def test_the_project_writes_every_digit_class_as_an_explicit_range() -> None:
    files = _python_files()
    problems: list[str] = []
    for path in files:
        for lineno, pattern in _offenders(path.read_text(encoding="utf-8")):
            problems.append(f"{path.relative_to(ROOT)}:{lineno}: {pattern!r}")
    assert not problems, (
        "these regexes use a Unicode-wide digit class. Python's \\d matches "
        "every Unicode decimal digit and int() converts them, which once let a "
        "fullwidth Month through with no finding. Write [0-9] instead:\n" + "\n".join(problems)
    )


def test_the_gate_actually_examined_the_engine() -> None:
    """A gate that scanned nothing reports success just as loudly as one that passed.

    The engine is where every digit regex in this project lives, so if the walk
    ever stops reaching it the gate has gone quiet rather than clean.
    """
    files = _python_files()
    assert ROOT / "src" / "qfer_preflight" / "engine.py" in files

    engine = (ROOT / "src" / "qfer_preflight" / "engine.py").read_text(encoding="utf-8")
    patterns = _regex_literals(engine)
    assert len(patterns) >= 4, (
        f"found only {len(patterns)} regex literals in engine.py, which is fewer "
        "than the digit patterns known to be there. The extractor has stopped "
        "seeing them and this gate now passes without checking anything"
    )


@pytest.mark.parametrize(
    "name",
    ["_FOUR_DIGIT_YEAR", "_SMALL_INT", "_NUMERIC_VALUE", "_COMPANY_NUMBER_DIGITS"],
)
def test_each_known_digit_regex_is_still_present_and_still_explicit(name: str) -> None:
    """Named individually, so deleting one cannot quietly shrink the gate's job."""
    engine = (ROOT / "src" / "qfer_preflight" / "engine.py").read_text(encoding="utf-8")
    line = next((ln for ln in engine.splitlines() if ln.startswith(f"{name} =")), None)
    assert line is not None, f"{name} has gone from engine.py"
    assert "[0-9]" in line, f"{name} no longer writes its digit class as [0-9]: {line}"
