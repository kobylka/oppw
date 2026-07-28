# Data lifecycle and recovery operations

## Policy

| Dataset | Online retention | Archive | Deletion |
|---|---|---|---|
| Immutable strategy authority and cash flows | Indefinite | Every database backup; backup copies follow the operator's recovery schedule | Never |
| Service-control audit | Indefinite | Every database backup; optional annual export retained indefinitely | Never |
| Market minute OHLC | Indefinite | Every database backup; online rows remain the canonical history | Never |
| Diagnostic events except `EXECUTION_STAGE` | 180 days | Exact encrypted archive for seven years | Only after archive verification |
| Legacy `EXECUTION_STAGE` diagnostics | Indefinite | Every database backup | Never through retention |
| Equity minute samples | 400 days | Exact encrypted archive for seven years | Only after daily rollup and archive verification |
| Equity daily projection | Indefinite | Every database backup | Rebuildable, but not routinely deleted |

All database timestamps and cutoffs are UTC. `strategy_equity_daily.equity_day` is the UTC date of the original minute samples, preserving the existing all-time grouping semantics.

## Disposable recovery drill

Run from a clean development checkout with Docker available:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\validate_backup_restore.ps1 -RepoRoot D:\oppw
```

The drill uses two disposable MySQL containers and synthetic records. It never reads a private backend configuration, contacts production, or leaves the dump behind. Success requires matching source/restored digests for all authoritative tables, service-control audit, market minutes, events, equity minutes, and daily equity; restored triggers must still reject authority mutation and market-minute deletion.

Target recovery objectives for the disposable fixture are an RPO of zero and an RTO below 30 minutes. Production backup frequency determines the production RPO and must be recorded by the operator.

## Production backup on the primary Windows machine

The registered task `OPPW MySQL Production Backup` runs every day at 02:15 in the Windows machine's local `Europe/Warsaw` time. `tools/install_mysql_backup_task.ps1` installs a protected runtime copy for the current Windows user; the task does not depend on a repository checkout remaining unchanged. It uses that user's interactive token without storing a Windows password because both Docker Desktop and the EFS private key are session-bound. If the user is logged out at 02:15, the start-when-available policy runs it after the next logon when Docker is available. `tools/backup_mysql.ps1` reads the ignored `Mobile/backend/config.php` through `tools/write_mysql_client_config.php`. The temporary MySQL option file is ACL-limited, credentials are never passed on a process command line, and the file is removed after the run.

The private configuration names the Docker-internal MySQL host. From this Windows machine the runner deliberately overrides only that host with `eloski.eu`; it retains the configured port, database, user, and password. The connection requires TLS. Each run creates a transactionally consistent dump with routines and triggers, compresses it directly to `D:\OPPW-Backups\mysql`, verifies SHA-256, and restores it into a disposable MySQL 8.4 container. A backup is published only after the restore contains all authority and operational tables and the expected trigger set. The canonical schema defines no MySQL scheduled events, so the production dump does not request the separate `EVENT` privilege.

The destination, backup artifacts, manifests, hash sidecars, and run logs use Windows EFS. Successful backups are retained in full for 35 days, then the latest successful backup in each UTC month is retained for up to 12 months. Encrypted run logs are retained for 180 days. With the daily schedule, the normal production RPO is at most 24 hours plus any retry delay; actual recovery time remains workload- and incident-dependent.

Install or refresh the task from this machine with:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\install_mysql_backup_task.ps1 `
  -RepoRoot D:\oppw `
  -DatabaseHost eloski.eu `
  -Destination D:\OPPW-Backups\mysql `
  -DailyAt 02:15 `
  -DockerPath 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' `
  -PhpPath 'C:\Users\kobyl\AppData\Local\Programs\PHP\current\php.exe'
```

EFS protects data at rest on this volume but does not protect against loss of this computer or its `D:` drive. Export the Windows user's EFS recovery certificate with `cipher /x` and store the password-protected PFX separately. Replicate verified backup artifacts to an encrypted off-machine destination before treating this as machine-loss protection. Do not copy decrypted database dumps or the private backend configuration into the repository.

## Retention command

The command is CLI-only and defaults to a non-mutating report:

```powershell
php .\Mobile\backend\admin\retention.php
php .\Mobile\backend\admin\retention.php --apply --archive-dir=D:\oppw-archives
```

Optional bounds are `--events-days`, `--equity-days`, `--batch-size`, and `--max-batches`. Retention-day overrides may lengthen the online period but cannot shorten the canonical 180/400-day minima. Production scheduling should run once daily during a low-traffic period. The archive directory must be outside the backend web root, encrypted at rest, replicated, and protected against overwrite. Only completed archive files whose SHA-256 matches the recorded retention run may be expired after the documented archive period.

The command never accepts a table name. Its only purge paths are ordinary `strategy_events` rows and old `strategy_equity_points`; it cannot delete authority, `EXECUTION_STAGE` compatibility events, service-control audits, or `strategy_market_points`.

## Failure and recovery

- An archive-write or hash failure stops before database mutation.
- A database failure rolls back rollup and deletion together; an unreferenced archive file may remain and can be removed after reconciliation.
- Re-running is safe because committed source rows are gone and uncommitted rows remain unchanged.
- A failed restore drill blocks release when invoked by `tools/release.ps1`.
- A failed production restore verification leaves no published `.sql.gz` backup; the `.partial` file is removed and Task Scheduler records a non-zero result.
- Production restoration always targets a new database. Never restore a drill over the active database.

## Index policy

The maintenance paths use `idx_event_retention_time(event_time,id)` and `idx_equity_retention_time(captured_minute,strategy_key)`; account-facing queries retain their account/time indexes. Preserve indexes supporting event pagination/name filters, equity account/time ranges, market account/time ranges, and service-control request/account-time lookups. The equity daily projection is keyed by `(strategy_key, equity_day)` and supplies all-time/long-window reads after minute retention. Drawdown analytics always prefer retained minute rows and label daily projection points as fallback history. Capture row counts, table sizes, slow-query evidence, and `EXPLAIN ANALYZE` output before any further index change. Do not remove primary-key-equivalent indexes without measured before/after validation on production-shaped disposable data.
