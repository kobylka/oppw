# Deploy OPPW Monitor 14.0.0

1. Upload `Mobile/backend/analytics.php` to the production backend.
2. Validate it on the server:

   ```powershell
   php -l Mobile/backend/analytics.php
   ```

3. Install the v14 APK over the existing app:

   ```powershell
   adb install -r Mobile/app/build/outputs/apk/debug/app-debug.apk
   ```

No SQL migration and no MT5 restart are required.
