# OPPW MT5 v51 — canonical strategy and immutable MySQL authority

Build: `2026-07-21-canonical-spec-immutable-authority-v51`

v51 adds a canonical, hash-addressed strategy specification and separates durable business records from the general diagnostic event stream.

## Authoritative MySQL records

- `strategy_specifications`: complete resolved strategy contract;
- `strategy_account_spec_assignments`: account adoption history;
- `strategy_decisions`: immutable, specification-linked decisions;
- `strategy_execution_stages`: normalized order lifecycle;
- `strategy_fills`: exact MT5 fills or explicitly non-exact reconciliation fills;
- `strategy_protection_changes`: SL/TP request and result history;
- `strategy_trade_ledger`: append-only OPENED/RECOVERED/CLOSED transitions;
- `account_cash_flows`: immutable deposits, withdrawals, and adjustments.

`strategy_trades` remains a mutable materialized projection for Analytics. `strategy_events` remains a diagnostic and legacy-compatibility stream; neither is the only historical authority.

## Required deployment order

1. Back up the database and repository.
2. Stop REAL and DEMO publisher/executor processes.
3. Run `Mobile/backend/sql/migrate_v51_strategy_authority.sql` once, after all older migrations.
4. Upload the PHP files in `Mobile/backend/` to the production backend.
5. Run `install_v51.ps1` to update both local runtime loops and backend source.
6. Start PUBLISHER first, then EXECUTOR, for each account.

Do not rerun older decision/cash-flow migrations after v51: v51 installs database triggers that deliberately reject changes to historical authority rows.

Example migration command:

```powershell
mysql -u YOUR_USER -p YOUR_DATABASE < .\Mobile\backend\sql\migrate_v51_strategy_authority.sql
```

Install repository files:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_v51.ps1 -RepoRoot D:\oppw
```

Private account config files are never overwritten. Only credential-free `*.example.py` templates are installed.

## Verification queries

```sql
SELECT spec_id,spec_hash,spec_version,strategy_build,execution_symbol,signal_symbol,created_at
FROM strategy_specifications ORDER BY created_at DESC;

SELECT strategy_key,decision_id,strategy_spec_id,strategy_spec_hash,recorded_at,outcome
FROM strategy_decisions ORDER BY id DESC LIMIT 20;

SELECT strategy_key,execution_id,stage,occurred_at,order_ticket,deal_ticket,side,volume
FROM strategy_execution_stages ORDER BY id DESC LIMIT 50;

SELECT strategy_key,position_ticket,side,fill_price,volume,deal_ticket,fill_source,is_exact,filled_at
FROM strategy_fills ORDER BY id DESC LIMIT 30;

SELECT strategy_key,position_ticket,change_stage,old_sl,new_sl,old_tp,new_tp,reason,occurred_at
FROM strategy_protection_changes ORDER BY id DESC LIMIT 30;
```

The authenticated read endpoint for stored specifications is `strategy-specifications.php?account=REAL` (or `DEMO`).

## Compatibility note

Historical pre-v51 execution stages remain readable through the diagnostic-event fallback in Analytics. v51 and later stages are read from `strategy_execution_stages` first. Broker-side exits observed only through position disappearance are stored as `is_exact=0`; v51 does not invent a deal ticket or claim an exact fill it did not receive from MT5.

