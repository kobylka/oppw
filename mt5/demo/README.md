# OPPW MT5 continuous v40

## Roles and accounts

The script accepts two independent selectors:

```powershell
python .\oppw_mt5_continuous.py --mode executor --account demo
python .\oppw_mt5_continuous.py --mode publisher --account demo
python .\oppw_mt5_continuous.py --mode executor --account real
python .\oppw_mt5_continuous.py --mode publisher --account real
```

`--mode executor` is the only role allowed to place or modify trades. `--mode publisher` is read-only.

`--account demo` loads:

```text
oppw-mt5-config.py
```

`--account real` loads:

```text
real-mt5-config.py
```

For compatibility, the script also accepts `oppw_mt5_config.py` and `real_mt5_config.py` when the hyphenated files are absent.

The default is:

```text
--mode executor --account demo
```

## Terminal banners

After every minute Trade Status, the executor prints:

```text
2026-07-18 11:39:25 INSTANCE_EXECUTOR [DEMO]
2026-07-18 11:39:25 AUTOTRADING_ENABLED
```

The role banner is bright yellow for EXECUTOR and bright cyan for PUBLISHER. The AutoTrading banner remains green/red.

The publisher prints:

```text
2026-07-18 11:39:25 INSTANCE_PUBLISHER [REAL]
```

## Account isolation

v40 automatically scopes runtime files by account. With default paths:

```text
oppw_mt5_state.demo.json
oppw_mt5_state.real.json
oppw_mt5.demo.lock
oppw_mt5.real.lock
oppw_monitor_equity.demo.json
oppw_monitor_equity.real.json
log/demo/
log/real/
```

Each account gets separate:

- executor lock;
- publisher lock;
- publisher heartbeat;
- backend-publishing lock;
- event spool;
- state file;
- equity-history file;
- logs.

The executor and publisher for the same account still coordinate with each other. A REAL publisher does not stop DEMO executor publishing, and vice versa.

The backend account key is forced to `DEMO` or `REAL` based on `--account`, preventing a selected config from publishing under the wrong account.

## Existing DEMO state

On first DEMO start, v40 copies existing legacy files when the new account-scoped files do not exist:

```text
oppw_mt5_state.json -> oppw_mt5_state.demo.json
oppw_monitor_equity.json -> oppw_monitor_equity.demo.json
```

The original files are left unchanged.

## MT5 login safety

The script verifies that the MT5 login returned by the terminal matches `Config.login` from the selected account file:

- mismatch at startup: process refuses to start;
- mismatch while running: connection becomes unhealthy and no trade request is allowed.

For simultaneous DEMO and REAL operation, use separate MT5 terminal installations/data directories and configure a different `terminal_path` in each config. Pointing both accounts at the same MT5 terminal can make the terminal switch accounts underneath the other process; v40 blocks trading on mismatch, but separate terminals are the correct setup.

## Convenience launchers

The package includes:

```text
run_demo_executor.bat
run_demo_publisher.bat
run_real_executor.bat
run_real_publisher.bat
```

## Configuration environment overrides

The selected config class still honors its existing `OPPW_*` environment variables. A globally set `OPPW_LOGIN`, `OPPW_SERVER`, `OPPW_TERMINAL_PATH`, or other override takes precedence over values inside either config file.
