# Current architecture

This document describes the present repository. It is deliberately not a changelog. Root `VERSION` supplies the product release identity; `Mobile/VERSION` independently supplies the Android application release identity.

## Canonical source map

| Concern | Canonical location |
|---|---|
| Product/MT5/backend/service version | `VERSION` |
| Android application version | `Mobile/VERSION` |
| MT5 strategy composition and sole entrypoint | `mt5/oppw_mt5_continuous.py` |
| MT5 cohesive runtime modules | `mt5/oppw_core/` |
| MT5 configuration schema/defaults | `mt5/oppw_core/settings.py` |
| MT5 configuration template | `mt5/oppw_mt5_config.example.py` |
| Demo/Real selection | canonical entrypoint with `--account demo|real` |
| MT5 regression tests | `mt5/tests/` |
| Android application | `Mobile/app/` |
| PHP API | `Mobile/backend/` |
| Base database schema | `Mobile/backend/sql/schema.sql` |
| Ordered migrations | `Mobile/backend/sql/migration-order.txt` |
| Release orchestration | `tools/release.ps1` |
| Repository invariants | `tools/validate_source.py` |
| Disposable MySQL validation | `tools/validate_mysql.ps1` |
| Disposable backup/restore validation | `tools/validate_backup_restore.ps1` |
| Production MySQL backup and restore verification | `tools/backup_mysql.ps1` |
| Production backup task installation | `tools/install_mysql_backup_task.ps1` |
| Executable cross-component contracts | `contracts/` and `tools/validate_contracts.py` |
| Windows service supervision | `service/` |
| Operational retention command | `Mobile/backend/admin/retention.php` |
| Data lifecycle runbook | `docs/DATA_LIFECYCLE.md` |

## Runtime topology

```text
MT5 terminal
  ↕ official MetaTrader5 Python bridge
canonical OPPW loop
  ├─ EXECUTOR role: decisions, globally fenced market orders and protection
  └─ PUBLISHER role: read-only status/event publication
       ↕ authenticated HTTPS
PHP backend
       ↕ transactions and immutable/idempotent records
MySQL
       ↕ authenticated read APIs
Android monitor (no trading capability)
```

The canonical entrypoint owns CLI parsing, account selection, MT5 connection bootstrap, and the composed `OPPWContinuousStrategy` type. Its `oppw_core` modules separately own configuration, persistent models, logging/utilities, coordination, publishing, exchange sessions and market data, position lifecycle, strategy decisions, monitoring, broker execution/protection, and runtime orchestration. This is one implementation assembled through the entrypoint, not a collection of independently executable strategy variants.

`oppw_core/settings.py` defines the only MT5 `Config` dataclass and every canonical default. Each ignored private account file contains only required connection/publishing credentials plus an optional `OVERRIDES` mapping. Effective configuration is constructed in a fixed order: canonical defaults, private overrides, `OPPW_*` environment overrides, and explicit CLI runtime flags. Startup logs the effective non-secret settings. `tools/migrate_mt5_config.py` converts legacy copied private `Config` classes only after exact reconstruction validation and atomically replaces the private source.

EXECUTOR and PUBLISHER ownership is coordinated globally through MySQL-backed leases exposed by `coordination.php`. Fencing tokens protect actions after takeover. Weekly entries use database idempotency so separate machines cannot legitimately claim the same account/week twice. Local filesystem locks are not authoritative.

Two Windows machines run the canonical `OPPWContinuousSupervisor` service as LocalSystem. The host locates the explicitly configured MetaTrader owner's active or disconnected Windows session and launches the Python supervisor and terminal children on that interactive desktop; it waits fail-closed while that user is logged out. The backend assigns all four Demo/Real Executor/Publisher children to the master while it is responsive, assigns them to the backup after master heartbeat expiry, and idles the backup when the master returns. MT5 children are attempted globally in Demo Executor, Real Executor, Demo Publisher, Real Publisher order. Each child atomically reports readiness only after terminal connection, account/symbol validation, and applicable AutoTrading validation; the supervisor permits only one unready child at a time and applies bounded per-role timeout/backoff so one failing account does not indefinitely block the other. This assignment controls process availability only; MySQL leases and fencing remain authoritative for role work and trading.

The LocalSystem code boundary under `%ProgramData%\OPPW` uses protected Administrators ownership and exact ACLs. Only SYSTEM and Administrators may modify `bin`, `OPPWServiceHost.exe`, or `service.json`; the runtime user has read/traverse access at the root for configuration and service-stop observation, and Modify access only in the dedicated `runtime` and `logs` trees. Re-running the elevated installer replaces legacy ownership and inherited permissions with this allowlist before registering or starting the service.

## Backend capability ownership

| Capability | Canonical endpoint/module |
|---|---|
| Shared authentication/database helpers | `lib.php` |
| Global leases, fencing and weekly claims | `coordination.php` |
| Snapshot and explicit authority ingestion | `ingest.php` |
| Event/lifecycle ingestion | `events-ingest.php` |
| Current mobile status | `status.php` |
| Mobile equity-curve period boundaries | `equity-periods.php` |
| Analytics | `analytics.php` |
| Event history | `events.php` |
| Accounts | `accounts.php` |
| Diagnostic mobile delivery acknowledgement | `mobile-receipt.php` |
| Latest authoritative trade | `oppw_latest_trade.php` |
| Strategy decision history | `strategy-decisions.php` |
| Strategy specification history | `strategy-specifications.php` |
| Immutable-record storage helpers | `authority.php` |
| Cash-flow ingestion | `cashflow.php` |
| Windows supervisor assignment and mobile desired state | `service-control.php` |

Authentication endpoints live under `Mobile/backend/auth/`; push endpoints live under `Mobile/backend/push/`; administrative endpoints are not mobile read APIs.

Paired mobile credentials cannot write strategy authority. `mobile-receipt.php` stores a fixed-name diagnostic acknowledgement in `strategy_events`; analytics may merge it into delivery-latency presentation, but it never creates a `strategy_execution_stages` row. Paired-device writes are otherwise limited to device-owned authentication/push metadata, unpairing, and explicitly granted service-control desired state.

Analytics accepts any positive rolling-week window and an explicit all-history request. Android exposes both directly and the backend returns whether all history was requested together with the available and effective week counts. Resource protection uses a maximum eight-account scope, bounded trade/lifecycle result sets, per-device and per-IP request limits, one in-flight analytics request per device, and queries constrained to the requested or complete available date range. Hot minute equity remains retention-bounded while older history uses the indefinite daily projection.

Browser administration fails closed unless its explicit feature token is present. Manual market/trade imports require an independent manual-admin token and reject reuse of the pairing-admin token. Browser forms require HTTPS, same-origin submission, request throttling, no-store responses, framing denial, a restrictive content policy, and a restrictive permissions policy.

Daily and weekly mobile equity curves use Europe/Warsaw period boundaries derived from the exchange-calendar `weekCashOpen`. On the first actual trading session of a week, both begin at the cash open (normally 15:30); when an explicitly identified manual position opened earlier that same day, its exact opening timestamp becomes the boundary. On subsequent trading days the daily curve begins at midnight while the weekly curve retains the first-session boundary. The MT5 publisher supplies the additive `position.manual` authority, and Android parses it without changing trading behavior.
Android also enforces the published weekly boundary while parsing status responses. This compatibility guard removes pre-open points from an older backend response and leaves an intentionally completed prior-week curve unchanged. It does not infer a boundary from a calendar-week timestamp, because only exchange-calendar `weekCashOpen` can identify a holiday-delayed first trading session.

Analytics portfolio risk metrics use a cash-flow-adjusted daily equity curve built from the first, lowest-minute, and closing portfolio equity points for each Warsaw weekday. Maximum percentage/currency drawdown, aggregate duration and depth, time under water, Recovery factor, the Calmar denominator, and Ulcer index use that curve. Intraday highs and ordinary minute oscillations do not create additional daily peaks or episodes, while the retained minute low prevents unrealized intraday loss from disappearing behind a daily close.

The drawdown episode list has a distinct authority. Closed-trade returns define episode membership, peaks, and recovery boundaries. The minute-equity stream within each trade-defined interval refines the starting equity timestamp, lowest point, depth, trough-to-recovery duration, and the current end of an ongoing episode. The response declares `episodeAuthority=CLOSED_TRADES_WITH_MINUTE_EQUITY_REFINEMENT`, counts every trade-defined episode, and transfers details only for episodes lasting at least 24 hours. Account/scope and rolling-window filters apply to the daily equity curve; each rolling window is anchored to the latest trade or equity observation for the selected accounts, whichever is later, so an ongoing episode continues through the current equity week even when no trade has closed there. Leverage, exit-reason, and class filters apply only to the closed-trade episode list. History without hot minute rows uses explicitly labeled `strategy_equity_daily` fallback points. Android gives analytics a 30-second read timeout while smaller API calls retain the normal 8-second timeout.

## Data authority

| Record type | Authority |
|---|---|
| Strategy specification | `strategy_specifications` |
| Account/spec adoption | `strategy_account_spec_assignments` |
| Strategy decision | `strategy_decisions` |
| Execution lifecycle stage | `strategy_execution_stages` |
| Fill | `strategy_fills` |
| Protection change | `strategy_protection_changes` |
| Trade transition | `strategy_trade_ledger` |
| Cash flow | `account_cash_flows` |
| Current mobile snapshot | `strategy_snapshots`, exactly one mutable projection row per account |
| Mobile analytics trade projection | `strategy_trades`, with protective-close price/reason recovered from `strategy_protection_changes` when event and flat snapshot delivery are separated |
| Diagnostics, mobile delivery receipts, and low-volume operational messages | `strategy_events` |
| Minute equity history and indefinite daily projection | `strategy_equity_points` and `strategy_equity_daily` |
| Minute market OHLC history | `strategy_market_points`, retained online indefinitely |
| Desired process state and supervisor heartbeat | `strategy_service_desired_state` and `strategy_supervisor_nodes` |
| Service-control audit | `strategy_service_control_events` |

Immutable authority records use deterministic identifiers and reject mutation. Projections may be rebuilt or enriched; diagnostics must not become the only record of a business event.

## Data lifecycle and recovery

`Mobile/backend/admin/retention.php` is the sole operational-history retention command. It is CLI-only, dry-run by default, takes a database advisory lock, writes and verifies bounded gzip NDJSON archives, and can delete only ordinary diagnostic events older than 180 days and complete UTC account-days of minute equity older than 400 days. Equity deletion and its indefinite daily rollup commit atomically. Hot-window drawdown analytics use minute history to retain each daily low and refine closed-trade episode troughs; older windows use the daily projection as an explicit fallback. Legacy `EXECUTION_STAGE` diagnostics remain available to the compatibility fallback.

Strategy authority, cash flows, service-control audits, and every `strategy_market_points` minute OHLC record stay online indefinitely. The database rejects market-minute deletion independently of the retention command. Index changes require production-shaped measurement; existing event, equity, market, and service-control access indexes remain canonical until evidence supports a forward migration.

`tools/validate_backup_restore.ps1` creates a consistent synthetic backup in one disposable MySQL instance, restores it into a second instance, compares authoritative and operational table digests, and retests immutable and market-retention triggers. The release gate runs this recovery drill after ordered migration validation. Deployment-owned encrypted archive and backup storage requirements are defined in `docs/DATA_LIFECYCLE.md` and ADR 0013.

The primary Windows machine also runs the `OPPW MySQL Production Backup` scheduled task daily at 02:15 local Warsaw time. It runs under the current user's interactive token so Docker Desktop and that user's EFS key are available; a missed logged-out start runs after the next logon. Its protected runtime copy reads credentials from ignored `Mobile/backend/config.php`, overrides only the Docker-internal host with the machine-reachable production host, requires TLS, writes compressed backups to the EFS-encrypted `D:\OPPW-Backups\mysql`, and publishes an artifact only after a disposable MySQL restore passes. It keeps 35 days of successful backups, the latest backup per UTC month for 12 months, and 180 days of encrypted run logs. This local destination requires separate encrypted off-machine replication to cover loss of the computer or `D:` drive.

## Android contract

`StatusApiClient.kt` is the transport boundary, `JsonParser.kt` is the JSON compatibility boundary, and `Models.kt` is the in-app model authority. The app calls the canonical account, status, analytics, events, receipt, authentication, and push endpoints. It never connects directly to MySQL and contains no trading operation.

Any payload change must follow `docs/CONTRACT_POLICY.md`.

## Version and release flow

MT5 build identity, strategy specification version, release archive, and manifest derive from root `VERSION`. Android `versionName` derives from `Mobile/VERSION`; its monotonically increasing `versionCode` uses the epoch formula documented in ADR 0007. The two release lines advance independently. Releases are reproducible outputs in ignored `dist/`; they are never alternative source trees.

The release gate requires a clean Git commit, canonical-source validation, Python compilation/tests, PHP lint, complete SQL migration validation in disposable MySQL, a disposable backup-and-restore drill, an actual PHP/MySQL/API-to-Android contract run, and Android tests/build.

## Runtime/private material

Populated account configs, backend `config.php`, Android `local.properties`, secrets, logs, state, equity caches, event spools, and build outputs remain local and ignored. Example files contain placeholders only.

The canonical loop loads exactly one private account configuration: `mt5/demo/demo_mt5_config.py` or `mt5/real/real_mt5_config.py`. Those files are override-only and ignored; configuration aliases, copied `Config` classes, and account-specific loop launchers are not supported.
