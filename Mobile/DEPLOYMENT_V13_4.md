# Deploy OPPW Monitor 13.4.0

1. Upload these files together to the production backend:

   - `backend/analytics.php`
   - `backend/lib.php`
   - `backend/mobile-receipt.php`

2. Validate them on a machine with PHP installed:

   ```powershell
   php -l Mobile/backend/analytics.php
   php -l Mobile/backend/lib.php
   php -l Mobile/backend/mobile-receipt.php
   ```

3. Refresh Analytics. Existing lifecycle metrics are recalculated from the full-precision `event_at` values already stored in `strategy_events.details`; no database migration or new trade is required.

4. Install the 13.4 APK over the existing application to display lifecycle timestamps with milliseconds:

   ```powershell
   adb install -r Mobile/app/build/outputs/apk/debug/app-debug.apk
   ```

No MT5 script or trading configuration change is required.
