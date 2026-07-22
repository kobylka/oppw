# MT5 runtime

The sole implementation is `oppw_mt5_continuous.py` in this directory.

Existing account-specific commands remain valid because `demo/oppw_mt5_continuous.py` and `real/oppw_mt5_continuous.py` are thin launchers for the canonical file:

```powershell
python .\mt5\demo\oppw_mt5_continuous.py --mode executor --account demo
python .\mt5\real\oppw_mt5_continuous.py --mode executor --account real
```

Use `--mode publisher` for the read-only publisher role. Global process coordination is performed through the MySQL lease and fencing system; there is no authoritative local lock.

Copy `oppw_mt5_config.example.py` into the appropriate account directory using the private configuration filename expected by the launcher. Never commit the populated file.

Do not create version-suffixed loop copies. Change the root `VERSION` file and use `tools/release.ps1` to validate and package a release.
