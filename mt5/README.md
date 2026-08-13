# MT5 runtime

The sole executable entrypoint and strategy composition root is `oppw_mt5_continuous.py` in this directory:

```powershell
python .\mt5\oppw_mt5_continuous.py --mode executor --account demo
python .\mt5\oppw_mt5_continuous.py --mode executor --account real
python .\mt5\oppw_mt5_continuous.py --mode executor --account demo --account-key DEMO_TMS
python .\mt5\oppw_mt5_continuous.py --mode executor --account real --account-key REAL_TMS
```

Use `--mode publisher` for the read-only publisher role. Global process coordination is performed through the MySQL lease and fencing system; there is no authoritative local lock.

Canonical runtime behavior is organized under `oppw_core/` by responsibility. Those modules are imported only through the composition root and are not alternate entrypoints. Account commands, services, tests, and deployments must continue invoking `oppw_mt5_continuous.py`.

Production continuity uses `service/install-service.ps1`, which launches these same canonical commands for every configured account and role. Do not create account-specific service wrappers.

The current Bossa accounts retain the stable legacy keys and private files `demo/demo_mt5_config.py` and `real/real_mt5_config.py`; their operator-facing names are `DEMO BOSSA` and `REAL BOSSA`. Prepared TMS files are `demo/demo_tms_mt5_config.py` and `real/real_tms_mt5_config.py`. Their private `OVERRIDES` set `required_balance_multiplier` to `1.5` and leave `live_enabled` false for deployment validation; Bossa retains the canonical `1.765`. Replace every TMS placeholder before enabling those accounts. Never commit populated files. Enter the five required credential values and add only intentional account-specific differences to `OVERRIDES`. Do not copy or define `Config`; the sole schema/default authority is `oppw_core/settings.py`.

The TMS private files may set `auto_acknowledge_high_risk_warning` to `True` when the operator authorizes automatic acceptance of the broker's exact Polish leveraged-instrument warning. The standard-library Windows watcher is active only around MT5 initialization, verifies that the dialog belongs to the configured terminal path, and refuses similar titles or controls. Keep the option disabled for accounts that do not require or authorize that acknowledgement.

TMS also overrides `mt5_initialize_timeout_seconds` to `120` because its broker authorization may continue after the official bridge's 60-second default expires. Service deployments use a 150-second readiness deadline so initialization remains bounded without killing a valid TMS startup prematurely.

TMS enables `separate_mt5_login_after_initialize`: the Python bridge attaches to the dedicated terminal first, then calls the official `login` operation with the private account credentials. This isolates IPC startup from the broker warning and authorization flow. Exact login, account type, symbols, and applicable AutoTrading are still checked before readiness.

Both TMS private files override `trade_symbol` and `signal_symbol` to the OANDA TMS name `US100.pro`. Bossa retains `US100`. Do not use one broker's symbol name in another account's configuration.

`--account` identifies the Demo/Real type directory. `--account-key` is the unique coordination, backend, state, log, and audit identity; it defaults to `DEMO` or `REAL`. Each concurrent broker login needs a separate MetaTrader installation and terminal path. Register named keys with `Mobile/backend/admin/register_account.php` before startup.

If a local private file still contains a copied `Config` class, migrate both accounts with:

```powershell
python .\tools\migrate_mt5_config.py --account all
```

The migration suppresses `OPPW_*` environment overrides while reading the legacy file, reconstructs every canonical field, validates exact equivalence, and atomically replaces the private file only after that check succeeds. Runtime precedence is canonical defaults → private `OVERRIDES` → `OPPW_*` environment variables → CLI runtime flags.

Do not create version-suffixed loop copies. Change the root `VERSION` file and use `tools/release.ps1` to validate and package a release.
