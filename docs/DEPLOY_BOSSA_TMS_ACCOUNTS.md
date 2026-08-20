# Bossa and TMS account deployment

This runbook adds `DEMO_TMS` and `REAL_TMS` beside the existing `DEMO` and `REAL` account identities on both supervised Windows nodes. The stable Bossa keys remain unchanged so historical leases, claims, trades, analytics, and audit links stay attached to the same accounts; only their display names become `DEMO BOSSA` and `REAL BOSSA`.

The prepared TMS private configurations use `required_balance_multiplier = 1.5`, fixed `hard_stop_ratio_override = 0.9465`, and remain `live_enabled = False` through initial deployment. With the canonical `sizing_multiplier = 20`, this permits a theoretical maximum effective exposure of `20 / 1.5 = 13.333x`, subject to broker volume steps and available margin. Bossa retains `1.765`, or approximately `11.331x` under the same simplifying limit, and leaves the hard-stop override disabled so its leverage-dependent stop logic is unchanged.

## 1. Build and back up

1. Complete the repository validation gate and commit the coherent release change. Do not include private account configurations or terminal installations in the commit.
2. Run `tools/release.ps1` only from that clean commit. Stage the same official archive on the backend, Master, and Backup machines, but do not switch the backend PHP code before its migration is applied.
3. Take and verify a production MySQL backup before applying the account migration.
4. Record the current `OPPWContinuousSupervisor` configuration and current enabled-account query result without recording its write token or account credentials.

## 2. Apply the backend migration once

On the database administration host, open the MySQL client using its normal secure credential flow:

```text
mysql --host=DB_HOST --user=DB_ADMIN --password
```

Select the OPPW database and source the final ordered migration using an absolute path appropriate to that host:

```sql
USE oppw;
SOURCE D:/oppw/Mobile/backend/sql/migrate_v56_2_bossa_tms_accounts.sql;
```

Do not replay `schema.sql`, earlier migrations, or this migration after it has been recorded as applied. Verify the result:

```sql
SELECT account_key, display_name, account_type, broker_account_id, enabled, sort_order
FROM monitor_accounts
WHERE account_key IN ('DEMO', 'REAL', 'DEMO_TMS', 'REAL_TMS')
ORDER BY sort_order, account_key;
```

Expected at this stage:

- `DEMO` is enabled and displayed as `DEMO BOSSA`;
- `REAL` is enabled and displayed as `REAL BOSSA`;
- `DEMO_TMS` and `REAL_TMS` exist but remain disabled.

After that verification succeeds, publish the staged backend PHP code.

## 3. Prepare isolated MT5 terminals on both nodes

While logged in as the Windows runtime user, install or copy one independent MetaTrader 5 terminal for every broker login. The new recommended paths are:

```text
D:\oppw\mt5\demo_tms\MetaTrader 5\terminal64.exe
D:\oppw\mt5\real_tms\MetaTrader 5\terminal64.exe
```

The `mt5/demo_tms/` and `mt5/real_tms/` installation trees are ignored by Git. Do not put account configuration files there. The canonical private files remain:

```text
D:\oppw\mt5\demo\demo_tms_mt5_config.py
D:\oppw\mt5\real\real_tms_mt5_config.py
```

On both Master and Backup:

1. Start each TMS terminal interactively as the service runtime user.
2. Sign in to the matching TMS Demo or Real account and confirm the server and account type.
3. Confirm that `US100` is available under the configured broker symbol names.
4. Keep the runtime user signed in. Locking or disconnecting the session is supported; logging out is not.
5. Do not point two account files at the same `terminal64.exe`.

## 4. Populate both private TMS configurations on both nodes

Set the five private constants in each ignored file: terminal path, login, password, server, and backend monitor write token. Keep the following overrides:

```python
OVERRIDES = {
    "config_name": "DEMO TMS",  # use "REAL TMS" in the Real file
    "auto_acknowledge_high_risk_warning": True,
    "mt5_initialize_timeout_seconds": 120.0,
    "high_risk_warning_timeout_seconds": 120.0,
    "separate_mt5_login_after_initialize": True,
    "required_balance_multiplier": 1.5,
    "hard_stop_ratio_override": 0.9465,
    "tsl1pre_market_exit_delay_seconds": 60.0,
    "trade_symbol": "US100.pro",
    "signal_symbol": "US100.pro",
    "live_enabled": False,
}
```

Do not copy the canonical `Config` class and never commit or transmit these files. Terminal paths may differ between nodes, but account identity and strategy overrides must agree.

`auto_acknowledge_high_risk_warning` is an explicit authorization to tick and confirm the exact Polish leveraged-instrument risk warning during MT5 startup. It is disabled by default and must not be enabled for an account unless its operator is authorized to make that acknowledgement. Successful use is logged as `HIGH_RISK_WARNING_ACKNOWLEDGED`.

Because environment values outrank private overrides and are shared by every child of a supervisor, check the runtime user's User and Machine environment scopes. Remove stale account-specific `OPPW_*` overrides, especially `OPPW_REQUIRED_BALANCE_MULTIPLIER`, `OPPW_HARD_STOP_RATIO_OVERRIDE`, `OPPW_LIVE`, `OPPW_TERMINAL_PATH`, and `OPPW_LOGIN`. A global hard-stop override would also alter Bossa. Per-account differences belong in the private files.

## 5. Coordinate backend enablement and the supervisor-list change

Backend enabled accounts and each supervisor's managed-account list must match exactly. Use this bounded cutover:

1. Stop `OPPWContinuousSupervisor` on Backup and then Master.

```powershell
Stop-Service -Name OPPWContinuousSupervisor
(Get-Service -Name OPPWContinuousSupervisor).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(40))
```

2. Confirm both services are stopped and allow existing child processes and leases to release. Do not manually kill unrelated Python or MT5 processes.
3. From the backend directory, register and enable both prepared accounts. Supply the real broker account IDs:

```powershell
php .\admin\register_account.php --account=DEMO_TMS --type=DEMO --display-name="DEMO TMS" --broker-account-id=123456 --sort-order=40
php .\admin\register_account.php --account=REAL_TMS --type=REAL --display-name="REAL TMS" --broker-account-id=654321 --sort-order=30
```

4. Verify that all four `monitor_accounts` rows are enabled and that TMS has `EXECUTOR` and `PUBLISHER` desired-state rows.

```sql
SELECT strategy_key, role_name, desired_running
FROM strategy_service_desired_state
WHERE strategy_key IN ('DEMO_TMS', 'REAL_TMS')
ORDER BY strategy_key, role_name;
```

5. Reinstall/update Master first and Backup second from elevated PowerShell, using the identical ordered account list:

```powershell
$accounts = @('DEMO:DEMO','DEMO:DEMO_TMS','REAL:REAL','REAL:REAL_TMS')
.\service\install-service.ps1 -NodeRole Master -Accounts $accounts -RepoRoot D:\oppw -PythonPath C:\Path\To\python.exe -RuntimeUser MACHINE\mt5user
```

Run the same command on Backup with `-NodeRole Backup`. Omit `-WriteToken` so the installer requests it through its secure prompt. The installer starts the service after updating it.

Do not display the complete `%ProgramData%\OPPW\service.json`, because it contains the backend write token. A safe configuration check is:

```powershell
$serviceConfig = Get-Content "$env:ProgramData\OPPW\service.json" -Raw | ConvertFrom-Json
$serviceConfig.nodeRole
$serviceConfig.managedAccounts | Format-Table accountType, accountKey
Get-Service OPPWContinuousSupervisor
```

## 6. Validate all four accounts in dry-run mode

The first rollout keeps TMS trading disabled. On Master, inspect `%ProgramData%\OPPW\logs\supervisor.log` and the per-process console logs. Require all of the following before live activation:

- Master reports `PROCESS_READY` for all four Executors and all four Publishers;
- Backup heartbeats successfully and does not run children while Master is healthy;
- `DEMO_TMS` and `REAL_TMS` report the expected broker login and account type;
- TMS logs contain `CONFIG_PROFILE ... GROWTH_1_500`, `default_multiplier=1.500`, and `EVENT DRY_RUN live_enabled=false`;
- Bossa logs still contain `GROWTH_1_765` and `default_multiplier=1.765`;
- TMS `CONFIG_EFFECTIVE` reports `hard_stop_ratio_override: 0.9465`, while both Bossa accounts report `hard_stop_ratio_override: 0.0`;
- TMS `CONFIG_EFFECTIVE` reports `tsl1pre_market_exit_delay_seconds: 60.0`, while both Bossa accounts retain `0.0`;
- each TMS immutable strategy specification contains `tsl1preMarketExitDelaySeconds: 60.0`;
- Mobile/API account lists show `DEMO BOSSA`, `REAL BOSSA`, `DEMO TMS`, and `REAL TMS` separately;
- the latest TMS strategy specification contains `growthRequiredBalanceMultiplier: 1.5` and `activeProfile: GROWTH_1_500`;
- no account shows login mismatch, symbol-selection failure, readiness timeout, or assignment-list mismatch.

If an existing paired device should see or control the TMS accounts, replace its grant list while preserving every existing account it still needs:

```powershell
php .\admin\set_device_accounts.php --device=0123456789abcdef0123456789abcdef --accounts=DEMO,REAL,DEMO_TMS,REAL_TMS --can-control-service=1
```

Omit or set `--can-control-service=0` for read-only devices.

## 7. Activate live trading separately

Live activation is a second, explicit operation after dry-run acceptance:

1. Ensure neither TMS account has an unmanaged open position.
2. Stop both supervisors so Master and Backup cannot load different live settings during failover.
3. Change only `live_enabled` to `True` in both TMS private files on both nodes. Keep `required_balance_multiplier = 1.5` and `hard_stop_ratio_override = 0.9465`.
4. As the runtime user on both nodes, confirm that each TMS terminal is connected to the expected login and that MT5 Algo Trading is enabled.
5. Start Master and wait for all eight children to become ready. TMS Executors must report `live=ENABLED autotrading=ENABLED`.
6. Start Backup and confirm that it remains unassigned while Master is healthy.
7. Verify backend heartbeats, leases, specification assignments, Mobile status, and account-specific logs. Do not submit a test order merely to prove deployment.

Start each node with:

```powershell
Start-Service -Name OPPWContinuousSupervisor
(Get-Service -Name OPPWContinuousSupervisor).WaitForStatus('Running', [TimeSpan]::FromSeconds(40))
```

Demo and Real may be activated on separate maintenance windows by leaving the other TMS file at `live_enabled = False` on both nodes.

## 8. Rollback

Before any TMS position exists, the safest rollback is to stop both supervisors, restore `live_enabled = False` in both TMS files on both nodes, start Master, and then start Backup. Leave the four-account list intact so backend/supervisor matching continues to pass.

If TMS must be removed from supervision entirely, stop both supervisors, set the TMS backend rows to disabled without deleting their history, reinstall both supervisors with only `DEMO:DEMO` and `REAL:REAL`, then start Master followed by Backup. Keep the migration applied; migrations and immutable account history are never rolled back or deleted.

If a TMS position is already open, do not disable its Executor or live mode without an explicit broker-side position and protection plan. Disabling the process also disables automated exit and protection management for that account.
