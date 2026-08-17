# Security Policy

## Reporting a vulnerability

Report privately through GitHub Security Advisories on this repository
("Security" tab, "Report a vulnerability"). Please do not open a public issue
for a security problem.

Expect an acknowledgement within 7 days and an assessment within 30 days.

## What counts as a security issue here

This tool reads filing data that is often commercially sensitive, and some of
it is eligible for confidential treatment. The properties worth protecting:

- **No exfiltration.** The tool must open no network connection and must
  transmit nothing. Any code path that reaches the network is a vulnerability,
  not a feature.
- **No retention.** The tool writes no cache, no log file and no temporary
  copy of input data. Report output goes to stdout and nowhere else.
- **No data in errors beyond what the caller supplied.** Findings quote cell
  values so a filer can locate a problem. Anything that widened that to whole
  rows or whole files in an unexpected destination would be a defect.

A crash, a wrong finding, or a missed finding is a correctness bug. Report it
as a normal issue. A **false clean**, where the tool reports a submission as
validated when it was not, should be reported as a security issue: it is the
failure mode this project exists to prevent.

## Supply chain

The runtime has no third-party dependencies; it uses the standard library
alone. Development dependencies are locked in `uv.lock`. CI pins every GitHub
Action to a full commit SHA, runs with a least-privilege top-level
`permissions:` block, and runs secret scanning, static analysis and dependency
auditing on every push and pull request.

## Scope

This project is an independent utility. It is not affiliated with, endorsed by
or approved by the California Energy Commission. Do not report issues about
the Commission's own systems here.
