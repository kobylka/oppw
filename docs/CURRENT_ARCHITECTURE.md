# Current architecture

This document describes the present repository. It is deliberately not a changelog. Root `VERSION` supplies the current release identity.

## Canonical source map

| Concern | Canonical location |
|---|---|
| Project version | `VERSION` |
| MT5 strategy/execution loop | `mt5/oppw_mt5_continuous.py` |
| MT5 configuration template | `mt5/oppw_mt5_config.example.py` |
| Demo/Real entrypoints | thin launchers in `mt5/demo/` and `mt5/real/` |
| MT5 regression tests | `mt5/tests/` |
| Android application | `Mobile/app/` |
| PHP API | `Mobile/backend/` |
| Base database schema | `Mobile/backend/sql/schema.sql` |
| Ordered migrations | `Mobile/backend/sql/migration-order.txt` |
| Release orchestration | `tools/release.ps1` |
| Repository invariants | `tools/validate_source.py` |
| Disposable MySQL validation | `tools/validate_mysql.ps1` |

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

EXECUTOR and PUBLISHER ownership is coordinated globally through MySQL-backed leases exposed by `coordination.php`. Fencing tokens protect actions after takeover. Weekly entries use database idempotency so separate machines cannot legitimately claim the same account/week twice. Local filesystem locks are not authoritative.

## Backend capability ownership

| Capability | Canonical endpoint/module |
|---|---|
| Shared authentication/database helpers | `lib.php` |
| Global leases, fencing and weekly claims | `coordination.php` |
| Snapshot and explicit authority ingestion | `ingest.php` |
| Event/lifecycle ingestion | `events-ingest.php` |
| Current mobile status | `status.php` |
| Analytics | `analytics.php` |
| Event history | `events.php` |
| Accounts | `accounts.php` |
| Mobile delivery acknowledgement | `mobile-receipt.php` |
| Latest authoritative trade | `oppw_latest_trade.php` |
| Strategy decision history | `strategy-decisions.php` |
| Strategy specification history | `strategy-specifications.php` |
| Immutable-record storage helpers | `authority.php` |
| Cash-flow ingestion | `cashflow.php` |

Authentication endpoints live under `Mobile/backend/auth/`; push endpoints live under `Mobile/backend/push/`; administrative endpoints are not mobile read APIs.

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
| Current mobile snapshot | `strategy_snapshots` projection |
| Mobile analytics trade projection | `strategy_trades` |
| Diagnostics and low-volume operational messages | `strategy_events` |

Immutable authority records use deterministic identifiers and reject mutation. Projections may be rebuilt or enriched; diagnostics must not become the only record of a business event.

## Android contract

`StatusApiClient.kt` is the transport boundary, `JsonParser.kt` is the JSON compatibility boundary, and `Models.kt` is the in-app model authority. The app calls the canonical account, status, analytics, events, receipt, authentication, and push endpoints. It never connects directly to MySQL and contains no trading operation.

Any payload change must follow `docs/CONTRACT_POLICY.md`.

## Version and release flow

MT5 build identity, strategy specification version, Android version name/code, release archive, and manifest derive from root `VERSION`. Releases are reproducible outputs in ignored `dist/`; they are never alternative source trees.

The release gate requires a clean Git commit, canonical-source validation, Python compilation/tests, PHP lint, complete SQL migration validation in disposable MySQL, and Android tests/build.

## Runtime/private material

Populated account configs, backend `config.php`, Android `local.properties`, secrets, logs, state, equity caches, event spools, and build outputs remain local and ignored. Example files contain placeholders only.
