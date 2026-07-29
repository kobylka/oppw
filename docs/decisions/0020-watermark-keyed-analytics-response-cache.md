# ADR 0020: Watermark-keyed analytics response cache

- Status: Accepted
- Date: 2026-07-29

## Context

Analytics deliberately supports complete retained history, but producing the response scans and combines bounded trade, lifecycle, cash-flow, minute-equity, and daily-equity data. A device can legitimately repeat an identical request after rotation, navigation, or refresh. Authentication rate limits and single-flight control prevent abuse and duplicate concurrent work, but they do not reuse a completed result.

## Decision

The backend keeps a server-side encoded-response cache for at most 120 seconds, with a 30-second default. Authentication, account authorization, rate limiting, normalized filter validation, and the per-device single-flight lock run before every cache lookup.

The request identity includes the database namespace, paired device, complete permitted-account presentation, resolved account scope, and normalized analytics filters. The cache key additionally includes a database watermark covering the selected accounts' trade projection, latest minute and daily equity, cash flows, execution stages, and analytics diagnostic events. A new trade, a changed trade projection, or a new/latest equity observation therefore changes the key without waiting for TTL expiry. Cached bytes are reused unchanged only when both the request identity and watermark match.

Entries live in a protected absolute directory outside the web root; relative, web-root-contained, and symbolic-link paths are rejected. Entries use hash-only filenames, are size-bounded, HMAC integrity-checked, permission-restricted, and read/written under file locks. File-cache or watermark failures bypass the optimization without failing analytics. Responses remain `no-store` for clients and intermediaries; this decision adds only a private backend cache.

## Consequences

- Identical repeated requests return identical JSON bytes while the data watermark is unchanged.
- New live trade or equity data invalidates the entry immediately; TTL remains a short fallback for data changes that do not advance a tracked latest observation.
- Authorization and throttling are never cached or bypassed.
- Separate devices and account-grant/filter combinations cannot reuse each other's response files.
- No database migration or Android contract change is required.
