# ADR 0026: Default full-history analytics and yearly class distribution

- Status: Accepted
- Date: 2026-08-06

## Context

The Android Analytics screen opened with an arbitrary four-week subset even when more retained history was available. Its class-distribution panel also split each yearly class into separate leverage rows, obscuring the requested year-over-year class mix.

Removing the existing `classDistribution.leverage` field or silently changing its meaning would break installed Android clients under the cross-component contract policy.

## Decision

Android initializes and resets Analytics with explicit all-history mode. Users may still apply any positive trailing-week duration.

The backend adds `classDistributionByYear`, grouped only by closing year and trade class. It contains `year`, `tradeClass`, `trades`, `profit`, and `tradeKeys`; leverage is not part of its identity or payload. The current Android panel consumes this canonical field. When connected to an older backend, its parser merges legacy leverage-split rows by year and class.

The old `classDistribution` field remains temporarily unchanged for installed-app compatibility. It may be removed only through a deliberate major contract transition or after support for every client requiring it has ended.

## Consequences

- Opening or resetting Analytics shows the maximum retained history by default.
- Each year/class pair appears once in the class-distribution panel regardless of the trades' leverage levels.
- The global leverage filter still narrows the complete analytics response when selected.
- Backend-first and Android-first deployment orders remain compatible.
