# MT5 runtime

The sole implementation and entrypoint is `oppw_mt5_continuous.py` in this directory:

```powershell
python .\mt5\oppw_mt5_continuous.py --mode executor --account demo
python .\mt5\oppw_mt5_continuous.py --mode executor --account real
```

Use `--mode publisher` for the read-only publisher role. Global process coordination is performed through the MySQL lease and fencing system; there is no authoritative local lock.

Production continuity uses `service/install-service.ps1`, which launches these same canonical commands for both accounts and roles. Do not create account-specific service wrappers.

Copy `oppw_mt5_config.example.py` to `demo/demo_mt5_config.py` or `real/real_mt5_config.py`. Never commit the populated file.

Do not create version-suffixed loop copies. Change the root `VERSION` file and use `tools/release.ps1` to validate and package a release.
