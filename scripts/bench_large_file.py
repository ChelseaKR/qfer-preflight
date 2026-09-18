"""A benchmark harness for large filings. Not part of `make verify`.

Run it when touching the reader:

    uv run python scripts/bench_large_file.py --rows 400000

It synthesizes a filing from the published CEC-1306A Schedule 1 header shape
in a temporary directory, validates it through the same entry point a filer's
run uses, and reports wall time together with peak resident set size for the
process. The numbers are informational: they exist so a change to the reader
can be compared against its predecessor, not to gate anything.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from types import ModuleType

from qfer_preflight.engine import validate_path
from qfer_preflight.profiles import get_profile

#: `resource` is Unix-only. Importing it at module scope made this script --
#: and `tests/test_bench_harness.py`, which loads it -- fail to import on
#: Windows, which nothing noticed until a Windows CI leg existed to notice it.
#: The annotation is what keeps the `None` real to the type checker; a bare
#: `resource = None` in the handler is narrowed away and the branch below then
#: reads as unreachable.
resource: ModuleType | None
try:
    import resource as _resource
except ModuleNotFoundError:  # pragma: no cover - taken only on Windows
    resource = None
else:  # pragma: no cover - taken only on a Unix
    resource = _resource

HEADER = (
    "CompanyNumber,Year,Month,CountyNumber,CustomerType,RateClass,NAICSCode,"
    "NumberofCustomers,SalesDeliveryAmount,Revenue"
)


def maxrss_to_mib(maxrss: int, platform: str = sys.platform) -> float:
    """Convert one `ru_maxrss` reading to MiB.

    The unit is platform dependent, which `getrusage(2)` states and which
    nothing in the reading itself reveals: bytes on macOS and the BSDs,
    kilobytes on Linux. Dividing by 1024 * 1024 unconditionally was right on
    the machine this script was written on and 1024 times too small on the
    only platform the project runs automatically, since every job in
    `ci.yml`, `release.yml` and `security.yml` is `runs-on: ubuntu-latest`.
    Too small is also the flattering direction for a number whose whole
    purpose is to show that memory stays bounded, and at one decimal place an
    ordinary run printed `0.0 MiB`, which reads as a broken harness rather
    than as a wrong unit.
    """
    bytes_per_unit = 1 if platform == "darwin" else 1024
    return maxrss * bytes_per_unit / (1024 * 1024)


def peak_rss_mib() -> float | None:
    """Peak resident set size in MiB, or ``None`` where the platform cannot say.

    `getrusage(2)` is Unix-only. Returning `0.0` on a platform without it
    would print a memory figure of zero for a process that plainly used
    memory -- a value that was never measured, rendered as one that was,
    which is the defect this whole project is written against. The caller
    prints the absence instead.
    """
    if resource is None:
        return None
    return maxrss_to_mib(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000)
    args = parser.parse_args()

    profile = get_profile("CEC-1306A-S1")
    before = peak_rss_mib()
    started = time.perf_counter()

    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, "synthetic.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(HEADER + "\r\n")
            for row_number in range(args.rows):
                county = (row_number % 58) + 1
                handle.write(
                    f"123,2025,{(row_number % 3) + 1},{county},B,"
                    f"RESIDENTIAL_OTHER,925190,10,1000.50,25\r\n"
                )
        written = time.perf_counter()
        report = validate_path(path, profile)

    finished = time.perf_counter()

    print(f"rows          : {args.rows:,}")
    print(f"status        : {report.status.value}")
    print(f"rows read     : {report.rows_read:,}")
    print(f"write time    : {written - started:.2f}s")
    print(f"validate time : {finished - written:.2f}s")
    peak = peak_rss_mib()
    if peak is None or before is None:
        print(f"peak RSS      : not measured -- {sys.platform} has no getrusage(2)")
    else:
        print(f"peak RSS      : {peak:.1f} MiB (baseline {before:.1f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
