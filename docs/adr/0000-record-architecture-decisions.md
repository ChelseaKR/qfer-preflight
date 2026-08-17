# 0000. Record architecture decisions

- Status: Accepted
- Date: 2026-08-17

## Context

This project makes claims about what a filing does and does not conform to.
Those claims are only worth anything if the reasoning behind them is on the
record and can be challenged later. Decisions about which rules exist, what
they cite, and what the tool refuses to assert need to survive past the commit
that introduced them.

## Decision

Architecture decisions are recorded as numbered Markdown files in `docs/adr/`,
using sequential four-digit prefixes. Each records Status, Context, Decision
and Consequences. An ADR is immutable once accepted; a later ADR supersedes it
rather than editing it in place.

Any change to the following requires an ADR:

- Adding, retiring, or changing the meaning of a rule identifier.
- Changing what the tool treats as evaluated versus unevaluated.
- Changing the fail-closed contract in any way.

## Consequences

Small changes carry a little more ceremony. In exchange, the question "why
does QP018 not check anything" has a durable answer that does not depend on
anyone remembering.
