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
| Named Demo/Real selection | canonical entrypoint with `--account demo|real` plus optional `--account-key` |
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

An account may explicitly opt into the Windows-only high-risk-warning acknowledger during MT5 connection bootstrap. The bounded watcher runs in the same interactive runtime-user session as the terminal, accepts only the exact configured terminal executable path and exact Polish warning title/checkbox/OK controls, and records acknowledgement or timeout in the account log. Because broker authorization can create the modal after `mt5.initialize` returns, the watcher continues until it acknowledges the dialog or reaches its configured timeout. The default is disabled; the two TMS private configurations opt in, while Bossa remains unaffected. This is operational startup automation and does not change strategy decisions, sizing, broker orders, or specification identity.

The MT5 bridge initialization timeout is a validated per-account operational setting. Bossa retains the official 60-second default behavior; TMS allows 120 seconds for its warning acknowledgement and slower broker authorization. The Windows supervisor readiness deadline is 150 seconds, leaving a bounded 30-second margin for account, symbol, AutoTrading, and readiness-file validation after a TMS bridge connection completes.

TMS uses a two-phase bridge bootstrap supported by the official API: `initialize` first attaches to its explicit dedicated terminal path without broker credentials, then `login` performs broker authorization with that account's private credentials. This prevents terminal creation, Python IPC attachment, broker login, and the modal acknowledgement from competing inside one combined call. The existing post-login expected-account, Demo/Real trade-mode, symbol, and AutoTrading checks remain mandatory. Bossa retains the established combined initialization path.

New-week entry loss controls are per-account MySQL authority exposed by `strategy-controls.php`. The active EXECUTOR reads the four-rule revision through its global fencing identity before a controlled entry. `PREMARKET_LOW` is one switch and one conjunctive condition: range ≥0.80% and close in the bottom 15% of that range. Every rule evaluates at the pre-open BUY action, normally 15:29:57 Europe/Warsaw for a 15:30 XNYS open. The fresh MT5 BUY price is the authoritative entry reference for gap and Tuesday normalization and is included in the premarket range/close-location inputs; an allowed BUY is dispatched in that same cycle rather than waiting for the 15:30 M1 bar. Weekly entry approvals, Monday defers, and final skips are shared across master/backup through `strategy_entry_rule_week_state`; the backend rejects stale control revisions, and immutable control/week-event tables retain the audit. Closed-trade pre-leverage returns and zero-return skipped weeks supply the two-outcome arithmetic input.

Completed-session historical closes have one broker-history authority shared by entry controls, leverage selection, daily-close processing, and position recovery. The runtime selects the latest valid MT5 M1 candle whose opening timestamp is strictly before the exchange-calendar close boundary; a 22:00 session therefore normally resolves to the 21:59 candle even if a broker supplies an after-hours candle opening at 22:00. Successful results are cached by symbol/session/boundary, while failures remain retryable, throttled, and fail-closed. `strategy_market_points` remains publisher-owned monitoring history and is never an executor fallback.

Before a weekly position opens, the dedicated PUBLISHER may read the same four-rule context under its own valid fenced lease, but it cannot record a weekly decision. Each flat-account what-if snapshot includes all four rules in canonical order, including disabled rules, applicability, outcome status, effect, and every live `{actual, operator, threshold, met}` condition. Gap and Tuesday-normalization previews use the current MT5 BUY price; premarket range and close-location also include that current price. Android joins these live evaluations with the latest mobile-authenticated enablement projection and renders the complete set on the Position screen.

Open-position loss protection has an independent per-account revision in `strategy_position_rule_controls`, exposed through the same canonical `strategy-controls.php` capability and paired-device operational-control grant. Its `OR5` switch defaults off. While enabled, the active EXECUTOR evaluates only the account terminal's previous completed M1 candle; the forming candle and publisher-owned `strategy_market_points` are never decision inputs. A valid OR5 signal requires the signal-bar low to be at least 0.50% below actual entry, its close at or below the low of the first five regular-session M1 candles, and the minimum low of an exact trailing 60-M1 window to be at least 1.50% below that window's first open. Persistence is one completed close. On the entry day the 60-minute window cannot begin before the later of cash open or the position-open minute; on later days it may begin at the configured same-day premarket start.

The executor does not retrospectively test the candle completed before startup, enablement, or a newly observed position-rule revision. Missing exact M1 bars, stale/missing backend authority, a stale fencing revision, or an unavailable control response cannot authorize a new OR5 exit; the existing broker hard stop remains active. A match is first stored in immutable `strategy_position_rule_trigger_events` under the current EXECUTOR lease and fencing token. Only then is `EXIT_SIGNAL` emitted and a fresh-bid, globally fenced OR5 market SELL attempted. That authorization is position-scoped and survives retry, executor failover, and a later Mobile toggle-off, so an already-triggered exit cannot be cancelled. Open-position snapshots expose the live OR5 comparisons and authorization status separately from flat-account entry controls.

`oppw_core/settings.py` defines the only MT5 `Config` dataclass and every canonical default. Account type (`DEMO` or `REAL`) selects the private directory, while a unique account key selects the config filename and supplies the stable backend, lease, claim, audit, state, log, and Mobile identity. The existing Bossa accounts retain keys/files `DEMO`/`demo_mt5_config.py` and `REAL`/`real_mt5_config.py`, preserving all historical authority while Mobile displays `DEMO BOSSA` and `REAL BOSSA`. Prepared TMS identities use keys/files `DEMO_TMS`/`demo_tms_mt5_config.py` and `REAL_TMS`/`real_tms_mt5_config.py`; their private overrides use a `1.5` required-balance multiplier instead of the Bossa/default `1.765` and a fixed `0.9465` hard-stop ratio at both strategy leverages. Bossa leaves the ratio override disabled and retains its leverage-dependent hard-stop formula. TMS backend rows remain disabled until credentials exist on both nodes. Each ignored private account file contains only required connection/publishing credentials plus an optional `OVERRIDES` mapping. Effective configuration is constructed in a fixed order: canonical defaults, private overrides, `OPPW_*` environment overrides, and explicit CLI runtime flags. Startup logs the effective non-secret settings. `tools/migrate_mt5_config.py` converts the two historical copied private `Config` classes only after exact reconstruction validation and atomically replaces the private source.

Broker-specific instrument names are also private account overrides. Bossa resolves execution and signal data to `US100`; OANDA TMS resolves both to `US100.pro`. Startup must select both resolved symbols before readiness, and each immutable strategy specification records the actual execution and signal symbols.

Sizing uses the selected symbol's MT5-reported minimum, step, and maximum volumes. Monitoring text renders the resulting volume without fixed two-decimal rounding so broker steps such as OANDA TMS `0.001` remain visible; this presentation rule does not alter the broker-derived sizing calculation.

Potential notional is derived from the same current-price MT5 margin result as required deposit: `requiredDeposit × sizingMultiplier`. It therefore updates with broker margin and account-currency conversion. A simulated one-percent `order_calc_profit` is not used as an exposure proxy because broker CFD profit and margin contract models can differ.

Android uses the same precision-preserving lot presentation for open positions and pre-trade what-if tickets: it renders up to eight broker decimals and removes only insignificant trailing zeroes. Values such as `0.002` and `0.295` therefore remain distinct instead of displaying as `0.00` or `0.30`.

The publisher retains up to 10,080 local equity samples for restart continuity, but includes only the latest 144 as the snapshot's compatibility fallback. The backend constructs authoritative daily, weekly, and all-time curves from `strategy_equity_points`; bounding the redundant fallback keeps mature-account ingestion below the 512 KiB request limit.

EXECUTOR and PUBLISHER ownership is coordinated globally through MySQL-backed leases exposed by `coordination.php`. Fencing tokens protect actions after takeover. Weekly entries use database idempotency so separate machines cannot legitimately claim the same account/week twice. Local filesystem locks are not authoritative.

Canonical four-account priority is `REAL` (Bossa), `REAL_TMS`, `DEMO` (Bossa), then `DEMO_TMS`. The supervisor applies that order separately to EXECUTOR and PUBLISHER startup regardless of configuration-list order. When multiple accounts become eligible for a BUY or market SELL together, account overrides stagger submission by `0.0`, `0.1`, `1.0`, and `1.5` seconds respectively. Broker-protection SL/TP operations bypass this scheduling delay and remain immediate. An unavailable higher-priority account does not block a healthy lower-priority account.

Two Windows machines run the canonical `OPPWContinuousSupervisor` service as LocalSystem. The host locates the explicitly configured MetaTrader owner's active or disconnected Windows session and launches the Python supervisor and terminal children on that interactive desktop; it waits fail-closed while that user is logged out. Each node has the same explicit ordered list of one to eight named account keys and types. The backend assigns every configured Executor/Publisher child to the master while it is responsive, assigns them to the backup after master heartbeat expiry, and idles the backup when the master returns. Enabled backend accounts and the supervisor list must match exactly. MT5 children are attempted globally with every configured Executor first in account-list order, followed by every Publisher in that order. Each child atomically reports readiness only after terminal connection, expected-login/symbol validation, and applicable AutoTrading validation; the supervisor permits only one unready child at a time and applies bounded per-role timeout/backoff so one failing account does not indefinitely block the others. Every concurrently managed broker login uses a distinct MetaTrader installation/terminal path. Assignment controls process availability only; MySQL leases and fencing remain authoritative for role work and trading.

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
| Cash-flow and manual-tax ingestion | `cashflow.php` |
| Windows supervisor assignment and mobile desired state | `service-control.php` |
| Per-account entry/position-rule controls, weekly defer/skip state, and OR5 trigger authorization | `strategy-controls.php` |

Authentication endpoints live under `Mobile/backend/auth/`; push endpoints live under `Mobile/backend/push/`; administrative endpoints are not mobile read APIs. Strategy decision and specification history both use the paired-device session boundary and enforce the selected account grant before reading immutable authority.

Paired mobile credentials cannot write specifications, decisions, execution stages, fills, protection changes, trade transitions, or position-rule triggers. `mobile-receipt.php` stores a fixed-name diagnostic acknowledgement in `strategy_events`; analytics may merge it into delivery-latency presentation, but it never creates a `strategy_execution_stages` row. Paired-device writes are otherwise limited to device-owned authentication/push metadata, unpairing, and the explicitly granted operational-control capability. That capability owns supervised-service desired state plus per-account entry- and position-rule toggles; weekly rule outcomes and OR5 trigger authorization still require a globally fenced EXECUTOR.

Analytics accepts any positive rolling-week window and an explicit all-history request. A rolling window is exactly `N * 7 * 24 hours`. With no date selection it ends at the latest selected-account trade or equity observation (exclusive by one millisecond, matching MySQL timestamp precision); an optional `window_end_date=YYYY-MM-DD` instead moves that fixed-duration window so it ends after the selected inclusive Europe/Warsaw calendar date. The selected date must fall between the first and latest available activity dates. All-history ignores a window date and uses the exact first-to-latest activity span; it remains the Android Analytics screen's default. Android exposes the duration and a bounded date picker, and the backend returns the selected date, complete available date bounds, available/effective week counts, and exact UTC query boundaries. Resource protection uses a maximum eight-account scope, bounded trade/lifecycle result sets, per-device and per-IP request limits, one in-flight analytics request per device, and queries constrained to the selected or complete available date range. Hot minute equity remains retention-bounded while older history uses the indefinite daily projection.

After those authentication, authorization, request-validation, throttling, and single-flight checks, analytics may reuse a completed encoded response from a private server-side cache. Entries default to a 30-second TTL and are isolated by database, paired device, full account grants, resolved account scope, and normalized filters. Their key also includes a selected-account data watermark covering trade projections, latest minute/daily equity, cash flows, execution stages, and relevant diagnostic events, so new live trade or equity data produces an immediate miss. Cached and uncached success bodies are byte-identical, while responses remain `no-store` to clients and intermediaries.

On a whole-response miss, analytics separately caches ordered raw input rows for completed Europe/Warsaw weeks. Segment identity includes the database, account scope, dataset, exact UTC boundaries, and applicable trade filters. The latest requested week is never a historical segment, and any range reaching the actual current week is queried live from that boundary onward. A 24-hour default segment TTL bounds stale late corrections to older weeks. Segment files share the response cache's protected, HMAC-verified, locked storage boundary; they do not bypass authentication or authorization. A calculation-specific streaming reducer consumes cached historical rows followed by live rows and retains only cash-flow-adjusted daily first/low/close points, provenance counts, portfolio entry flows, and exact minute refinement state for closed-trade episodes. It avoids constructing minute chart/episode state that the daily authority discards, while leaving the API payload and Android contract unchanged.

Filtered-performance return metrics compound every closed trade in the effective window as `product(1 + trade return) - 1`, independently for pre-leverage price returns and leveraged account returns. Their weekly geometric equivalents use `pow(compounded growth factor, 1 / closed trade count) - 1`; only filtered closed trades participate in the numerator and denominator, while open trades are excluded. The API and Android model expose these values as percentage points.

Manual tax charges use the existing immutable `account_cash_flows` authority with flow type `TAX` and are written only through `cashflow.php`. The endpoint stores tax as a negative amount, makes identical stable-reference retries idempotent, and rejects a reference reused with different content. Tax is accounting-only: it does not change top-ups, withdrawals, net contributions, broker-equity cash-flow adjustment, or trading drawdown. Analytics exposes its positive magnitude together with pre-tax trading profit/return and explicit after-tax net profit/return; Android shows all of them in its Capital, cash flows and tax card. A separate observed broker balance movement remains `TOP_UP`, `WITHDRAWAL`, or `ADJUSTMENT` authority.

The Analytics yearly class-distribution panel groups filtered closed trades by closing year and trade class only. Leverage remains a global analytics filter but is not a dimension inside that panel. The canonical additive `classDistributionByYear` payload contains no leverage field; the older leverage-split `classDistribution` field remains temporarily for installed-app compatibility, and the current parser can merge that legacy shape when connected to an older backend.

Browser administration fails closed unless its explicit feature token is present. Manual market/trade imports require an independent manual-admin token and reject reuse of the pairing-admin token. Browser forms require HTTPS, same-origin submission, request throttling, no-store responses, framing denial, a restrictive content policy, and a restrictive permissions policy.

Enabled Firebase push stores its short-lived OAuth token only in an explicitly configured private directory outside the web root. The directory and cache file are locked, symlinks are rejected, POSIX permissions are restricted to `0700`/`0600`, and no shared-system-temp fallback exists. Web-server configuration is deployment-owned and intentionally absent from the repository; deployments must expose only canonical HTTP endpoints and deny source, SQL, tests, examples, publisher code, and documentation.

Daily and weekly mobile equity curves use Europe/Warsaw period boundaries derived from the exchange-calendar `weekCashOpen`. On the first actual trading session of a week, both begin at the cash open (normally 15:30); when an explicitly identified manual position opened earlier that same day, its exact opening timestamp becomes the boundary. On subsequent trading days the daily curve begins at midnight while the weekly curve retains the first-session boundary. The MT5 publisher supplies the additive `position.manual` authority, and Android parses it without changing trading behavior.
Android also enforces the published weekly boundary while parsing status responses. This compatibility guard removes pre-open points from an older backend response and leaves an intentionally completed prior-week curve unchanged. It does not infer a boundary from a calendar-week timestamp, because only exchange-calendar `weekCashOpen` can identify a holiday-delayed first trading session.

Android presents operational and trading timestamps in `Europe/Warsaw` independently of the device time-zone setting. Immutable `ACCEPTED` and `EXIT_ACCEPTED` lifecycle stage names remain unchanged in the contract, while failed instances are labeled `REJECTED` and `EXIT_REJECTED` in the UI so a broker rejection cannot appear to be an accepted order.

Analytics portfolio risk metrics use a cash-flow-adjusted daily equity curve built from the first, lowest-minute, and closing portfolio equity points for each Warsaw weekday. Maximum percentage/currency drawdown, aggregate duration and depth, time under water, Recovery factor, the Calmar denominator, and Ulcer index use that curve. Intraday highs and ordinary minute oscillations do not create additional daily peaks or episodes, while the retained minute low prevents unrealized intraday loss from disappearing behind a daily close.

The drawdown episode list has a distinct authority. Closed-trade returns define episode membership, peaks, and recovery boundaries. An episode starts when its first drawdown-causing trade opens, or at the preceding closed-trade peak if overlapping trades make that later; flat time before the new exposure is not counted as drawdown. The minute-equity stream within each trade-defined interval refines the starting equity value, lowest point, depth, trough-to-recovery duration, and the current end of an ongoing episode without replacing that start timestamp. The response declares `episodeAuthority=CLOSED_TRADES_WITH_MINUTE_EQUITY_REFINEMENT`, counts every trade-defined episode, and transfers details only for episodes lasting at least 24 hours. Account/scope and rolling-window filters apply to the daily equity curve; each rolling window is anchored to the latest trade or equity observation for the selected accounts, whichever is later, so an ongoing episode continues through the current equity week even when no trade has closed there. Leverage, exit-reason, and class filters apply only to the closed-trade episode list. History without hot minute rows uses explicitly labeled `strategy_equity_daily` fallback points. Android gives analytics a 30-second read timeout while smaller API calls retain the normal 8-second timeout.

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
| Cash flow and manual tax charge | `account_cash_flows`; `TAX` is accounting-only while `TOP_UP`, `WITHDRAWAL`, and `ADJUSTMENT` represent broker-equity movements |
| Current mobile snapshot | `strategy_snapshots`, exactly one mutable projection row per account |
| Mobile analytics trade projection | `strategy_trades`; exact market-exit and broker-protection close price/reason comes from completed MT5 deal history published to `strategy_fills`/`EXIT_FILLED` and outranks snapshot or protection fallbacks |
| Diagnostics, mobile delivery receipts, and low-volume operational messages | `strategy_events` |
| Minute equity history and indefinite daily projection | `strategy_equity_points` and `strategy_equity_daily` |
| Minute market OHLC history | `strategy_market_points`, retained online indefinitely |
| Desired process state and supervisor heartbeat | `strategy_service_desired_state` and `strategy_supervisor_nodes` |
| Service-control audit | `strategy_service_control_events` |
| Entry-rule settings and immutable setting audit | `strategy_entry_rule_controls` and `strategy_entry_rule_control_events` |
| Weekly entry-rule projection and immutable transition audit | `strategy_entry_rule_week_state` and `strategy_entry_rule_week_events` |
| Position-rule settings and immutable setting audit | `strategy_position_rule_controls` and `strategy_position_rule_control_events` |
| Position-scoped OR5 exit authorization | immutable `strategy_position_rule_trigger_events` |

Immutable authority records use deterministic identifiers and reject mutation. Projections may be rebuilt or enriched; diagnostics must not become the only record of a business event.

Execution lifecycle identity is correlated at the whole-execution level before analytics filters are applied. Entry stages may legitimately carry position ticket `0` until MT5 makes the position visible; a later stage's definitive ticket links the complete execution without rewriting those immutable early rows. A trade projection keeps the entry decision that authorized the execution, while later flat-account what-if decisions remain separate immutable decisions. Broker-triggered SL/TP exits have an exact `EXIT_FILLED`/`CLOSED` path and no executor market-SELL request stages; Android labels the absent `EXIT_CHECKED`, `EXIT_SENT`, and `EXIT_ACCEPTED` stages as not applicable.

Raw MT5 tick, bar, position, and deal epochs represent broker-server wall-clock values. The runtime attaches the configured strategy timezone (`Europe/Warsaw` by default) before converting authoritative lifecycle timestamps to UTC, including DST, so immediate `EXIT_FILLED` and later same-deal `CLOSED` reconciliation cannot differ by the local UTC offset.

Both snapshot and event-only ingestion treat an execution stage's offset-bearing `details.event_at` as authoritative. The surrounding log-envelope time is a compatibility fallback only because a naive envelope clock cannot safely identify UTC versus workstation-local time.
Analytics also projects that preserved explicit timestamp for historical non-fill stages that snapshot ingestion previously shifted. Historical exact `EXIT_FILLED`/`CLOSED` rows retain their persisted authority because older broker-deal payload timestamps were affected by a separate conversion defect.

## Data lifecycle and recovery

`Mobile/backend/admin/retention.php` is the sole operational-history retention command. It is CLI-only, dry-run by default, takes a database advisory lock, writes and verifies bounded gzip NDJSON archives, and can delete only ordinary diagnostic events older than 180 days and complete UTC account-days of minute equity older than 400 days. Equity deletion and its indefinite daily rollup commit atomically. Hot-window drawdown analytics use minute history to retain each daily low and refine closed-trade episode troughs; older windows use the daily projection as an explicit fallback. Legacy `EXECUTION_STAGE` diagnostics remain available to the compatibility fallback.

Strategy authority, cash flows, service-control audits, entry-rule controls and audits, and every `strategy_market_points` minute OHLC record stay online indefinitely. The database rejects market-minute deletion independently of the retention command. Index changes require production-shaped measurement; existing event, equity, market, service-control, and entry-rule access indexes remain canonical until evidence supports a forward migration.

`tools/validate_backup_restore.ps1` creates a consistent synthetic backup in one disposable MySQL instance, restores it into a second instance, compares authoritative and operational table digests, and retests immutable and market-retention triggers. The release gate runs this recovery drill after ordered migration validation. Deployment-owned encrypted archive and backup storage requirements are defined in `docs/DATA_LIFECYCLE.md` and ADR 0013.

The primary Windows machine also runs the `OPPW MySQL Production Backup` scheduled task daily at 02:15 local Warsaw time. It runs under the current user's interactive token so Docker Desktop and that user's EFS key are available; a missed logged-out start runs after the next logon. Its protected runtime copy reads credentials from ignored `Mobile/backend/config.php`, overrides only the Docker-internal host with the machine-reachable production host, requires TLS, writes compressed backups to the EFS-encrypted `D:\OPPW-Backups\mysql`, and publishes an artifact only after a disposable MySQL restore passes. It keeps 35 days of successful backups, the latest backup per UTC month for 12 months, and 180 days of encrypted run logs. This local destination requires separate encrypted off-machine replication to cover loss of the computer or `D:` drive.

## Android contract

`StatusApiClient.kt` is the transport boundary, `JsonParser.kt` is the JSON compatibility boundary, and `Models.kt` is the in-app model authority. The app calls the canonical account, status, analytics, events, receipt, authentication, push, service-control, and strategy-control endpoints. It never connects directly to MySQL or submits orders. An explicitly privileged paired device may change per-account service desired state and entry-rule enablement.

Any payload change must follow `docs/CONTRACT_POLICY.md`.

## Version and release flow

MT5 build identity, strategy specification version, release archive, and manifest derive from root `VERSION`. Android `versionName` derives from `Mobile/VERSION`; its monotonically increasing `versionCode` uses the epoch formula documented in ADR 0007. The two release lines advance independently. Releases are reproducible outputs in ignored `dist/`; they are never alternative source trees.

The release gate requires a clean Git commit, canonical-source validation, Python compilation/tests, PHP lint, complete SQL migration validation in disposable MySQL, a disposable backup-and-restore drill, an actual PHP/MySQL/API-to-Android contract run, and Android debug/release tests/builds. MT5 runtime wheels are exact-version and SHA-256 locked for Windows CPython 3.13. Android bootstrapping pins both the official Gradle wrapper JAR and distribution hashes, while strict Gradle verification metadata covers resolved executable plugin and dependency artifacts. IDE-only `*-sources.jar` and `*-javadoc.jar` attachments plus the exact pinned Gradle source ZIP are filename-scoped trust exceptions because Android Studio resolves them during model import but they are not executed by the build.

## Runtime/private material

Populated account configs, backend `config.php`, Android `local.properties`, secrets, logs, state, equity caches, event spools, and build outputs remain local and ignored. Example files contain placeholders only.

The canonical loop loads exactly one ignored private account configuration derived from its Demo/Real type and account key. Those files are override-only; configuration aliases, copied `Config` classes, and account-specific loop launchers are not supported. Named backend accounts are registered through `Mobile/backend/admin/register_account.php`, which uses the existing multi-account authority tables and initializes desired-state and entry-control projections.
