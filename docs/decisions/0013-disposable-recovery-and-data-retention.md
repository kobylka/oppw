# ADR 0013: Disposable recovery drills and bounded operational retention

- Status: Accepted
- Date: 2026-07-28

## Context

The database contains immutable business authority together with higher-volume operational series. Migration validation proves that a fresh schema can be created, but it does not prove that a transactionally consistent backup can restore authoritative rows, relationships, hashes, and immutability triggers. Operational history also needs explicit lifecycle rules so cleanup cannot accidentally remove business authority or the minute OHLC record.

## Decision

Every release gate performs a disposable MySQL backup-and-restore drill. The drill applies the ordered migrations, seeds representative authoritative and operational records, creates a consistent dump including triggers, restores it into a second clean MySQL instance, compares deterministic table digests, and verifies that immutable mutations remain rejected. It uses synthetic credentials and data only.

The primary Windows machine performs the corresponding production operation every day at 02:15 local Warsaw time. A scheduled task runs the canonical production backup script from a protected per-user runtime directory under the user's interactive token, which keeps the Docker Desktop session and user-bound EFS key available without storing a Windows password. Missed logged-out starts run after the next logon. It reads the ignored backend configuration through a short-lived ACL-limited MySQL option file, requires TLS, streams a consistent compressed dump into the EFS-encrypted `D:\OPPW-Backups\mysql`, verifies its SHA-256, and restores it into disposable MySQL before publishing it. Credentials never appear in the task definition or process arguments. The local schedule retains all successful backups for 35 days and the latest successful backup per UTC month for 12 months; encrypted operational logs remain for 180 days. The EFS recovery certificate and a verified off-machine replica remain operator responsibilities.

Retention classes are fixed as follows:

- strategy specifications, account/specification assignments, decisions, execution stages, fills, protection changes, trade transitions, cash flows, and service-control audit records remain online indefinitely and are never deleted by retention tooling;
- every `strategy_market_points` minute OHLC row remains online indefinitely; an explicit database trigger rejects deletion;
- ordinary diagnostic events remain hot for 180 days, are exported exactly before deletion, and are retained in encrypted archive storage for seven years;
- legacy `EXECUTION_STAGE` diagnostic events remain online because analytics may use them as a compatibility fallback;
- equity minute samples remain hot for 400 days, are exported exactly into encrypted archive storage retained for seven years before deletion, and are summarized into an indefinite daily projection used by all-time and long-window analytics.

The canonical retention command is CLI-only, dry-run by default, single-owner through a database advisory lock, bounded by batch count and size, and refuses to operate without a writable archive directory. An archive file is closed and SHA-256 verified before the corresponding database transaction may roll up or delete rows. Retention runs record their source range, row count, archive name, digest, status, and completion time.

Index changes require measured query plans. Primary-key-equivalent historical indexes are not removed speculatively. Daily equity reads use the bounded projection; current daily and weekly curves continue to use minute samples.

## Consequences

- Backup success means verified recoverability rather than successful dump creation alone.
- Production has a concrete daily schedule and encrypted local destination, with a worst-case normal RPO of 24 hours plus retry delay.
- Immutable authority, service-control audit history, and minute market OHLC history cannot be shortened by routine retention.
- Event and equity archives are operational recovery material, not alternate business authority.
- Retention, restore, schema, API, and Android-parser behavior remain part of the release gate.
- Archive storage encryption, immutability, replication, and seven-year expiry are deployment responsibilities documented in the data-lifecycle runbook.
- The local EFS destination alone does not cover machine or volume loss; an exported EFS recovery certificate and encrypted off-machine replication are required for that threat.
