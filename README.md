# OPPW

OPPW is a continuously supervised MetaTrader 5 trading system with a PHP/MySQL authority backend and a read-only Android monitoring app. One canonical strategy source serves Demo and Real accounts; runtime roles, global coordination, audit records, analytics, service failover, and mobile monitoring are maintained in the same repository.

The product/MT5/backend/service release line is defined only by `VERSION`. The independently versioned Android release line is defined only by `Mobile/VERSION`.

## System overview

```text
MetaTrader 5
    |
    | official MetaTrader5 Python bridge
    v
Canonical OPPW runtime
    |-- EXECUTOR: decisions, globally fenced orders and protection
    `-- PUBLISHER: read-only snapshots, market/equity history and events
            |
            | authenticated HTTPS
            v
PHP API <-> MySQL authority and projections
            |
            | paired-device access tokens
            v
Android monitor (no trading capability)
```

Two Windows machines may run the continuous supervisor as Master and Backup. The backend assigns processes according to node health, while MySQL leases, fencing tokens, and weekly-entry claims remain the final authority preventing duplicate work or trading.

## Repository map

| Area | Canonical ownership |
|---|---|
| `mt5/oppw_mt5_continuous.py` | Sole MT5 executable entrypoint and strategy composition root |
| `mt5/oppw_core/` | Cohesive runtime modules used by the canonical entrypoint |
| `mt5/oppw_core/settings.py` | MT5 configuration schema and default authority |
| `mt5/oppw_mt5_config.example.py` | Only committed MT5 account-configuration template |
| `mt5/tests/` | Canonical strategy and runtime regression tests |
| `Mobile/backend/` | PHP ingestion, coordination, read APIs and administration |
| `Mobile/backend/sql/` | Base schema and ordered forward-only migrations |
| `Mobile/app/` | Kotlin/Jetpack Compose Android monitor |
| `service/` | Two-node Windows supervisor, service host and installer |
| `contracts/` | Executable publisher-to-MySQL-to-API-to-Android contract fixtures |
| `tools/` | Source, migration, recovery, contract, backup and release validation |
| `backtest/` | Research and artificial historical exports; not a production entrypoint |
| `docs/` | Architecture, strategy, lifecycle, release and decision records |

## Runtime and safety guarantees

- `mt5/oppw_mt5_continuous.py` is the only executable strategy entrypoint. Account-specific launchers and copied strategy trees are unsupported.
- Demo/Real selection uses `--account demo|real`; execution/publication selection uses `--mode executor|publisher`.
- Configuration precedence is canonical defaults, private account `OVERRIDES`, `OPPW_*` environment variables, then explicit CLI flags.
- Execution ordering, global leases/fencing, deterministic authority identifiers, weekly-entry claims, and immutable audit links are enforced across machines.
- The Android app reads authenticated projections and has no order, position-modification, or market-closure capability.
- Live trading is never part of compilation, unit tests, contract tests, or disposable database validation.

## Initial setup

Release validation requires Python 3, PHP CLI, Docker with a running engine, MySQL 8, JDK 17, the Android SDK, and the Windows .NET Framework C# compiler. MetaTrader 5 and the official Python bridge are required on trading machines. Host-specific executable paths are intentionally kept out of this project overview.

### MT5 account configuration

Copy `mt5/oppw_mt5_config.example.py` to the exact ignored private path for each configured account:

- Demo: `mt5/demo/demo_mt5_config.py`
- Real: `mt5/real/real_mt5_config.py`

Each private file contains only the five required credential constants and an optional `OVERRIDES` mapping. It must not copy or define the canonical `Config` class. Migrate historical copied configurations with:

```powershell
python .\tools\migrate_mt5_config.py --account all
```

Run the canonical process directly during development:

```powershell
python .\mt5\oppw_mt5_continuous.py --mode executor --account demo
python .\mt5\oppw_mt5_continuous.py --mode publisher --account demo
python .\mt5\oppw_mt5_continuous.py --mode executor --account real
python .\mt5\oppw_mt5_continuous.py --mode publisher --account real
```

### Backend and database

Copy `Mobile/backend/config.example.php` to the ignored `Mobile/backend/config.php` and provide the database connection, independent authentication secrets, and publisher write token. Production requires HTTPS.

For a fresh database, apply every non-comment entry in `Mobile/backend/sql/migration-order.txt` from top to bottom. For an existing database, apply only migrations that have not already run, preserving their order. Apply migrations before deploying PHP that depends on them; never replay `schema.sql` or edit deployed migration history.

Backend authentication is capability-specific:

- MT5 ingestion and coordination use the publisher write token.
- Mobile reads use short-lived paired-device access tokens and per-account grants.
- Pairing and manual administration use separate optional tokens and remain disabled unless needed.

`Mobile/backend/health.php` is the unauthenticated database-health endpoint. Canonical mobile capabilities are owned by `status.php`, `analytics.php`, `events.php`, `accounts.php`, and the other endpoints listed in `docs/CURRENT_ARCHITECTURE.md`.

### Android

Copy `Mobile/local.properties.example` to the ignored `Mobile/local.properties`, set the HTTPS API base URL, and optionally configure Firebase values. Build and test from `Mobile/`:

```powershell
.\gradlew.bat testDebugUnitTest assembleDebug
```

The transport boundary is `StatusApiClient.kt`, JSON compatibility belongs to `JsonParser.kt`, and `Models.kt` owns in-app API models. Cross-component payload changes must update producer, persistence, API, parser/model, fixtures, and tests together.

### Windows continuous supervisor

Install the same supervisor on two Windows machines from elevated PowerShell, choosing one Master and one Backup:

```powershell
.\service\install-service.ps1 -NodeRole Master -RepoRoot D:\oppw -PythonPath C:\Path\To\python.exe -RuntimeUser MACHINE\mt5user
.\service\install-service.ps1 -NodeRole Backup -RepoRoot D:\oppw -PythonPath C:\Path\To\python.exe -RuntimeUser MACHINE\mt5user
```

The service runs as LocalSystem and launches canonical MT5 children in the configured runtime user's active or disconnected interactive session. The runtime user must remain signed in; locking or disconnecting is supported.

## Analytics and data lifecycle

Portfolio drawdowns are calculated by the backend from cash-flow-adjusted `strategy_equity_points` minute equity. Maximum percentage and currency drawdown, episodes, duration, time underwater, Recovery factor, the Calmar denominator, and Ulcer index all share this authority. Exact statistics are computed before the chart series is bounded for Android.

Minute equity remains hot for 400 days. Retention atomically creates indefinite `strategy_equity_daily` projections before removing eligible minute rows, and older analytics explicitly report daily fallback granularity. `strategy_market_points` minute OHLC history and immutable strategy authority remain online indefinitely.

`Mobile/backend/admin/retention.php` is the only operational retention command. Production backup and restore behavior is defined in `docs/DATA_LIFECYCLE.md`; `tools/backup_mysql.ps1` publishes a backup only after a disposable restore succeeds.

## Validation and release

Every change starts with `AGENTS.md`, preserves unrelated working-tree changes, and follows `docs/CHANGE_CHECKLIST.md`. Cross-component changes additionally follow `docs/CONTRACT_POLICY.md`.

Run the complete validation gate without packaging:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release.ps1 -RepoRoot D:\oppw -ValidateOnly
```

Create a release only from a clean commit:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release.ps1 -RepoRoot D:\oppw
```

The gate validates canonical layout, Python compilation and tests, the Windows service host, PHP lint/tests, ordered MySQL migrations, synthetic backup/restore, the live-shaped cross-component contract, and the Android tests/build. Successful packaging creates `dist/OPPW-<VERSION>.zip` plus checksums. `dist/` remains ignored because releases are reproducible outputs, not source.

## Documentation

- `docs/CURRENT_ARCHITECTURE.md` — current ownership, topology and data authority
- `docs/STRATEGY_SPECIFICATION.md` — canonical strategy behavior
- `docs/CONTRACT_POLICY.md` — payload, persistence and compatibility rules
- `docs/CHANGE_CHECKLIST.md` — required implementation and validation scope
- `docs/RELEASE_PROCESS.md` — reproducible validation and packaging
- `docs/DATA_LIFECYCLE.md` — retention, backup, restore and archive requirements
- `docs/decisions/` — accepted Architecture Decision Records

Generated builds, archives, IDE state, logs, locks, credentials, populated configs, backend secrets, and Android local properties must remain untracked.
