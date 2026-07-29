# ADR 0021: Completed-week analytics input segments

- Status: Accepted
- Date: 2026-07-29
- Extends: ADR 0020

## Context

The watermark-keyed encoded-response cache eliminates identical repeated work only while selected-account data is unchanged. Active publishers add minute equity continuously, so the watermark changes and a legitimate refresh must miss that cache. Full-history analytics then repeatedly retrieves hundreds of thousands of immutable historical minute rows even though almost all completed weeks are unchanged.

## Decision

After authentication, authorization, request validation, rate limiting, single-flight acquisition, and a whole-response cache miss, analytics partitions its input window at Europe/Warsaw week boundaries. Ordered raw input rows for each completed week are stored independently. Segment identity includes the database namespace, account keys, dataset and exact UTC range; filtered trade segments additionally include all trade filters.

The latest requested week is always queried live. When the requested range reaches the actual current Warsaw week, that week and any future fixture range are one live tail. This prevents normal minute-equity publication from invalidating or rebuilding completed historical segments while ensuring the newest relevant data is read from MySQL on every response-cache miss.

Completed segments use the same protected absolute cache directory, HMAC integrity verification, hash-only filenames, file locks, size bounds and restrictive permissions as response entries. Their TTL defaults to 24 hours and is bounded between five minutes and 30 days. The TTL deliberately bounds staleness when a late correction or retention transformation changes an older completed week. Cache failure is an optimization miss, not an analytics failure.

The canonical analytics calculations consume cached historical rows followed by the live rows in the same ordering as the former full-window queries. Response fields and units do not change. Authentication and authorization are never cached or bypassed. No database migration or Android contract change is required.

## Consequences

- Continuous current-week equity updates still invalidate the whole response but no longer force MySQL to rescan completed weeks.
- Cold requests populate independent weekly segments; later windows reuse every overlapping completed week.
- Late corrections to completed history may take up to the configured segment TTL to appear unless the private segment cache is cleared during deployment or repair.
- Segment storage grows with distinct database/account/dataset/filter/week combinations and is pruned opportunistically after expiry.
- PHP still performs the canonical cross-week calculation with the calculation-specific reducer accepted by ADR 0022, preserving drawdown continuity and exact cached/uncached semantics.
