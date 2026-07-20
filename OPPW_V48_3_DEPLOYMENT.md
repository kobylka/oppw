# Deploy OPPW v48.3 publication lifecycle correction

Replace both active MT5 loop copies while they are stopped:

```powershell
Copy-Item .\mt5\oppw_mt5_continuous_v48_3.py D:\oppw\mt5\demo\oppw_mt5_continuous.py -Force
Copy-Item .\mt5\oppw_mt5_continuous_v48_3.py D:\oppw\mt5\real\oppw_mt5_continuous.py -Force
```

Upload `Mobile/backend/analytics.php` to the production backend.

Keep `Mobile/backend/mobile-receipt.php` deployed. After restarting the relevant publisher/executor, open the app Overview once. A successful status refresh creates the actual `MOBILE_RECEIPT` stage for the active execution.

The startup log must contain:

```text
build=2026-07-20-publication-lifecycle-v48.3
```

No SQL migration or trade is required. The current open execution receives `PUBLISHED` from its first successful v48.3 snapshot.
