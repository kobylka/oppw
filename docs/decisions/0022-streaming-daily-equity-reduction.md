# ADR 0022: Streaming daily-equity reduction

- Status: Accepted
- Date: 2026-07-29
- Extends: ADR 0016 and ADR 0021

## Context

Completed-week input segments removed repeated historical MySQL scans, but the daily-equity analytics path still passed every cached minute through the general drawdown analyzer. That analyzer built and repeatedly downsampled a minute chart, calculated minute-defined drawdown episodes, and then discarded both before calculating the authoritative daily result. A production-shaped DEMO profile contained about 504,000 equity minutes but only 980 retained daily first/low/close points; cache file decoding was a small fraction of the warm request.

## Decision

Daily-equity analytics uses a dedicated streaming prepass. It preserves the exact cash-flow-adjusted equity index, each Warsaw weekday's first point, lowest adjusted minute point and close, minute/daily-fallback provenance counts, portfolio account-entry flows, trade links, and the minute refinement state for closed-trade episodes. It does not construct minute chart points, general minute drawdown episodes, or minute aggregate statistics that the daily authority never consumes.

Canonical UTC database timestamps use allocation-free normalization. Warsaw day boundaries are calculated once per observed day, including DST transitions, instead of creating timezone objects for every minute. Closed-trade episode boundaries use equivalent canonical UTC string comparisons; final elapsed and recovery durations retain the existing timestamp authority.

The retained daily rows still pass through the canonical drawdown analyzer, and closed trades still define episode membership and recovery. The response shape, values, units, source-granularity labels, and Android contract do not change. No database migration is required.

## Consequences

- Historical minute rows remain available for exact daily lows and trade-episode trough refinement without paying for discarded minute presentation state.
- A back-to-back production-shaped profile reduced the 504,000-row prepass from about 36 seconds to about 7 seconds on the primary workstation; deployment performance remains environment-dependent.
- The general drawdown analyzer remains canonical for retained daily rows and direct minute-analysis callers.
- Regression coverage compares every reducer output consumed by daily analytics with the former general-analyzer prepass across cash flows, a Warsaw DST boundary, daily fallback, weekends, and trade episodes.
- No API, persistence, or Android migration is required.
