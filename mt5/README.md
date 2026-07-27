# MT5 runtime

The sole executable entrypoint and strategy composition root is `oppw_mt5_continuous.py` in this directory:

```powershell
python .\mt5\oppw_mt5_continuous.py --mode executor --account demo
python .\mt5\oppw_mt5_continuous.py --mode executor --account real
```

Use `--mode publisher` for the read-only publisher role. Global process coordination is performed through the MySQL lease and fencing system; there is no authoritative local lock.

Canonical runtime behavior is organized under `oppw_core/` by responsibility. Those modules are imported only through the composition root and are not alternate entrypoints. Account commands, services, tests, and deployments must continue invoking `oppw_mt5_continuous.py`.

Production continuity uses `service/install-service.ps1`, which launches these same canonical commands for both accounts and roles. Do not create account-specific service wrappers.

Copy `oppw_mt5_config.example.py` to `demo/demo_mt5_config.py` or `real/real_mt5_config.py`. Never commit the populated file. Enter the five required credential values and add only intentional account-specific differences to `OVERRIDES`. Do not copy or define `Config`; the sole schema/default authority is `oppw_core/settings.py`.

If a local private file still contains a copied `Config` class, migrate both accounts with:

```powershell
python .\tools\migrate_mt5_config.py --account all
```

The migration suppresses `OPPW_*` environment overrides while reading the legacy file, reconstructs every canonical field, validates exact equivalence, and atomically replaces the private file only after that check succeeds. Runtime precedence is canonical defaults → private `OVERRIDES` → `OPPW_*` environment variables → CLI runtime flags.

Do not create version-suffixed loop copies. Change the root `VERSION` file and use `tools/release.ps1` to validate and package a release.
