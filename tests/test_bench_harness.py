"""The benchmark harness reports memory in the unit it prints.

`scripts/bench_large_file.py` is what `README.md` sends a reader to for the
numbers behind the bounded-memory claim, and it sits outside `make verify`, so
nothing exercised its arithmetic. The one step in it a reader cannot check by
looking is the `ru_maxrss` conversion: `getrusage(2)` returns bytes on macOS
and the BSDs and kilobytes on Linux, and Linux is the only platform this
project runs automatically.

These tests pin that conversion from both sides, so the harness cannot go back
to being right on the author's laptop and wrong everywhere CI runs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bench_large_file.py"

# One real reading, expressed in each platform's own unit.
REAL_MIB = 27.0
AS_BYTES = int(REAL_MIB * 1024 * 1024)
AS_KILOBYTES = AS_BYTES // 1024


def _load_bench() -> ModuleType:
    """Import the script by path; `scripts/` is not a package."""
    assert SCRIPT.exists(), f"{SCRIPT} is missing"
    spec = importlib.util.spec_from_file_location("bench_large_file", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BENCH = _load_bench()


def test_both_platform_conventions_describe_the_same_memory() -> None:
    """The same resident memory reports the same MiB on macOS and on Linux."""
    on_macos = BENCH.maxrss_to_mib(AS_BYTES, "darwin")
    on_linux = BENCH.maxrss_to_mib(AS_KILOBYTES, "linux")
    assert on_macos == on_linux == REAL_MIB


def test_a_linux_reading_is_not_divided_as_though_it_were_bytes() -> None:
    """Regression: the old divisor understated Linux by 1024x, and flatteringly.

    27 MiB of real memory printed as `0.0 MiB` at one decimal place, which is
    both wrong and unreadable as wrong.
    """
    was_printed = round(AS_KILOBYTES / (1024 * 1024), 1)
    assert was_printed == 0.0, "the old arithmetic no longer reproduces"
    assert BENCH.maxrss_to_mib(AS_KILOBYTES, "linux") == REAL_MIB


def test_the_conversion_reads_the_running_platform_by_default() -> None:
    assert BENCH.maxrss_to_mib(AS_BYTES) == BENCH.maxrss_to_mib(AS_BYTES, sys.platform)


def test_a_reading_from_this_process_is_a_plausible_figure() -> None:
    """A live call has to land in a range no unit error could reach.

    The interpreter plus the test suite is never under 1 MiB, and the 1024x
    error puts an ordinary run below that, so this fails on the wrong unit
    without pinning a number that depends on the machine.

    On a platform with no `getrusage(2)` the reading is `None` -- an absence,
    not a zero -- and the assertion is that it says so rather than producing
    a figure. Skipping instead would leave the Windows leg reporting a pass
    over a function it never called.
    """
    reading = BENCH.peak_rss_mib()
    if BENCH.resource is None:
        assert reading is None, (
            f"the platform has no getrusage(2) but peak_rss_mib returned a number: {reading!r}"
        )
        return
    assert reading is not None
    assert 1.0 < reading < 100_000.0, reading


def test_an_unmeasurable_peak_is_absent_rather_than_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discriminates on every platform, including the ones that can measure.

    Without this the Unix legs never execute the branch that matters, and the
    only evidence that a missing `resource` produces an absence rather than a
    `0.0` would be the Windows job.
    """
    monkeypatch.setattr(BENCH, "resource", None)
    assert BENCH.peak_rss_mib() is None
