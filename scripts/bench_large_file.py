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
import resource
import tempfile
import time

from qfer_preflight.engine import validate_path
from qfer_preflight.profiles import get_profile

HEADER = (
    "CompanyNumber,Year,Month,CountyNumber,CustomerType,RateClass,NAICSCode,"
    "NumberofCustomers,SalesDeliveryAmount,Revenue"
)


def peak_rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


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
    print(f"peak RSS      : {peak_rss_mib():.1f} MiB (baseline {before:.1f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
