# OPPW Monitor v9.1 deployment checklist

1. Upload the complete `backend/` directory while preserving your private `config.php`.
2. No SQL migration is required.
3. The optional health threshold may be added to `config.php`; the default is 60 seconds:

```php
'monitor_price_warning_seconds' => 60,
```

4. Replace the Android project while preserving `local.properties`.
5. Open the project in Android Studio, synchronize Gradle, and install over the current app to preserve pairing.
6. MT5 v38 is unchanged; do not replace the running MT5 script for this correction.
7. Verify on Saturday/Sunday with no open position:
   - Phase: `Weekend`
   - Regime: `None`
   - Next action: `None`
   - no OH countdown
8. Verify Overview shows:
   - `Health: OK/UNKNOWN/WARNING`
   - `Heartbeat: …`
   - `Last tick: …`
9. Verify the all-time chart shows both Equity and the dashed Deposits-to-date line.
