"""Offline pre-submission validator for CEC QFER Consumption CSV filings.

This project is an independent utility. It is not affiliated with, endorsed
by, or approved by the California Energy Commission.

The names in `__all__` are the supported Python surface. Everything else in
this package is private and may move without notice. See `api.py` for what
the surface commits to, and the README for the stability policy.

    from qfer_preflight import validate

    report = validate("filing.csv")
    print(report.status, report.error_count)
    print(report.to_text())

`__version__` is bound before the submodules are imported, because `engine`
reads it from this module at import time.
"""

__version__ = "0.2.0"

from .api import (
    Advisory,
    Citation,
    Finding,
    NotEvaluated,
    Profile,
    ProfileDetectionError,
    Report,
    Rule,
    Severity,
    Status,
    ValidationInputError,
    detect_profile,
    list_profiles,
    list_rules,
    validate,
)

__all__ = [
    "Advisory",
    "Citation",
    "Finding",
    "NotEvaluated",
    "Profile",
    "ProfileDetectionError",
    "Report",
    "Rule",
    "Severity",
    "Status",
    "ValidationInputError",
    "__version__",
    "detect_profile",
    "list_profiles",
    "list_rules",
    "validate",
]
