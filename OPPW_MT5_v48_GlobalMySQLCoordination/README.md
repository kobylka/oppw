# OPPW MT5 v48 — global MySQL coordination

Build:

```text
2026-07-20-global-mysql-leases-v48.1
```

v48 removes filesystem locks as an ownership mechanism. EXECUTOR and PUBLISHER
leadership is global for each account key, so copies launched from different
folders or computers coordinate through the same MySQL database.

v48.1 includes the startup deadlock correction: the asynchronous publisher
checks database ownership and logs publication-state changes outside its event
queue condition lock.

## Coordination model

`strategy_runtime_leases` contains three lease names per account:

| Lease | Lifetime | Purpose |
|---|---:|---|
| `EXECUTOR` | 15 seconds by default | Only holder may perform strategy execution work |
| `PUBLISHER` | 15 seconds by default | Only holder owns normal snapshot publication |
| `TRADE_EXECUTION` | 10 seconds maximum | Serializes one concrete BUY, SELL, or SL/TP operation |

Each takeover increments a monotonically increasing fencing token. The backend
rejects stale owners and stale tokens. Role leases renew every three seconds by
default. A process stops its role when it can no longer renew before the safety
margin. Database time, not a workstation clock, determines expiry.

Immediately before every `mt5.order_send()` the EXECUTOR:

1. proves that its EXECUTOR lease is current;
2. acquires the account's `TRADE_EXECUTION` gate;
3. validates the new gate fencing token;
4. performs the single MT5 request;
5. releases the gate.

The BUY path additionally claims `(account, ISO week)` in
`strategy_weekly_entries` before `order_send()`.

Weekly-entry states:

- `CLAIMED`: reserved before the broker call;
- `ACCEPTED`: MT5 accepted or placed the order;
- `REJECTED`: definitely not accepted and may be retried by a later execution;
- `UNKNOWN`: the broker result was not knowable; automatic retry remains blocked.

`UNKNOWN` deliberately fails safe. Inspect the MT5 account and broker history
before changing it manually. Never mark it `REJECTED` merely to make a retry run.

## Backend files

- `coordination.php`: atomic lease, gate, and weekly-entry operations;
- `events-ingest.php`: fenced event-only ingestion from either active role;
- `ingest.php`: normal snapshot ingestion with lease validation;
- `lib.php`: common validation of role owner and fencing token;
- `sql/migrate_v48_global_leases.sql`: tables and historical-entry backfill.

When a dedicated PUBLISHER lease is active, an EXECUTOR cannot publish a normal
snapshot. It can still persist its own execution events through
`events-ingest.php`; this replaces the old shared JSONL event spool.

## Required configuration additions

Merge these fields from `oppw_mt5_config.example.py` into each ignored private
account config:

```python
coordination_url = "https://YOUR_HOST/oppw-backend/coordination.php"
events_ingest_url = "https://YOUR_HOST/oppw-backend/events-ingest.php"
coordination_timeout_seconds = 5.0
role_lease_ttl_seconds = 15.0
role_lease_heartbeat_seconds = 3.0
role_lease_safety_margin_seconds = 2.0
publisher_presence_check_interval_seconds = 1.0
trade_gate_ttl_seconds = 10.0
trade_gate_max_hold_seconds = 5.0
```

The write token and account key must match the deployed backend. Both URLs and
the normal ingest URL must use HTTPS.

Remove obsolete settings from private configs:

```text
lock_file
publisher_heartbeat_interval_seconds
publisher_heartbeat_stale_seconds
event_spool_lock_timeout_seconds
event_spool_lock_retry_seconds
```

State, weekly log, and equity-history files remain local data files. They are
not ownership authorities and are not consulted when granting a role or trade
permission.

## Deployment

1. Back up MySQL and the repository.
2. Stop all old EXECUTOR and PUBLISHER processes on every computer.
3. Run `Mobile/backend/sql/migrate_v48_global_leases.sql` once.
4. Upload `lib.php`, `ingest.php`, `coordination.php`, and `events-ingest.php`.
5. Merge the v48 fields into the ignored Demo and Real configs.
6. Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_v48.ps1 -RepoRoot D:\oppw
```

7. Start PUBLISHER first, then EXECUTOR, using the same balance-multiplier flag
   for both processes when `--legacy-balance-multiplier` is selected.

The installer never overwrites private account configs. It moves obsolete v47
lock, heartbeat, and event-spool files into a timestamped archive under `mt5`.

## Expected startup output

```text
EVENT GLOBAL_LEASE_ACQUIRED role=EXECUTOR account=DEMO ... fencing_token=...
...
2026-07-20 15:29:00 AUTOTRADING_ENABLED
2026-07-20 15:29:00 LIVE_ENABLED
```

`LIVE_DISABLED` is printed in red when dry-run mode is active. The line is
always printed immediately after the AutoTrading banner.

Starting a second same-role process for the same account fails with the current
holder's host, PID, owner ID, and expiry. A different account has independent
leases.

## Operations

Inspect active ownership:

```sql
SELECT strategy_key, lease_name, owner_id, fencing_token, hostname, process_id,
       build_id, heartbeat_at, expires_at, operation_kind, operation_id
FROM strategy_runtime_leases
ORDER BY strategy_key, lease_name;
```

Inspect weekly entry protection:

```sql
SELECT strategy_key, week_key, status, execution_id, decision_id,
       attempt_count, order_ticket, deal_ticket, retcode, error_text, updated_at
FROM strategy_weekly_entries
ORDER BY week_key DESC, strategy_key;
```

Do not delete an active lease to force a takeover. Stop the owner and wait for
expiry, or allow normal shutdown to release it. If the backend/database is
unavailable, new v48 processes do not start and a running process fails closed
before its lease becomes unsafe.

## Limits

The MySQL fence cannot be passed into the broker's MT5 protocol. v48 therefore
validates the short trade gate immediately before the synchronous API call and
prevents another process from acquiring that gate until expiry. Weekly-entry
idempotency handles the more important crash-after-BUY ambiguity durably.

Events waiting only in process memory can be lost if that process is killed
before the backend accepts them. Trading ownership and weekly-entry claims are
already durable in MySQL and do not depend on that event queue.
