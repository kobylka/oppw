# OPPW Monitor Android v10.1

Complete Android Studio project built from the working v9.1 mobile application.

## Authentication

The v9.1 authentication implementation is retained intact:

```text
app/src/main/java/com/oppw/monitor/auth/AuthModels.kt
app/src/main/java/com/oppw/monitor/auth/SecureSessionStore.kt
app/src/main/java/com/oppw/monitor/data/StatusApiClient.kt
app/src/main/java/com/oppw/monitor/data/StatusRepository.kt
```

The v9.1 response parser is also retained. Pairing reads the nested `session` object returned by `auth/pair.php`, including access token, refresh token, expiry timestamps, device and allowed accounts. Sessions remain AES/GCM-encrypted with Android Keystore alias `oppw_monitor_session_key_v1`.

This project does not contain the reconstructed v10 `ApiClient.kt` or `SessionStore.kt`.

## v10.1 behavior

- Saturday and Sunday are derived in `Europe/Warsaw` locally. Even when Friday's close failed and a position remains open, Overview shows `Weekend`, regime `None`, next action `None`, and no OH countdown. The position remains visible with a carried-position warning.
- Daily, weekly and all-time equity charts derive horizontal coordinates from actual timestamps. Sampling density no longer changes elapsed-time spacing.
- The condition shown in `Closest condition` is removed from `All other conditions` by matching name, source and target price.
- Sharpe and Sortino use only closed-trade returns returned by the analytics API. The preferred return is `profit / balanceBefore`; explicit return fields and `profitPercent` are supported fallbacks. Metrics are unannualized and display `N/A` with fewer than five valid closed trades or an undefined denominator.
- Routine condition checks are hidden from the first Logs render. The setting starts off per account, is sent to `events.php` as `hide_routine=1`, and is additionally enforced in the Android list.
- The v9.1 account selector, refresh-token flow, encrypted session store, notifications, Firebase integration, WorkManager and unpairing are preserved.

## Configure

Copy `local.properties.example` to `local.properties`, preserve Android Studio's `sdk.dir`, and set:

```properties
OPPW_API_BASE_URL=https://your-domain.example/oppw-backend/
```

The URL must use HTTPS. Firebase values remain optional.

## Build

Open the project in Android Studio using JDK 17 and install Android SDK 37 when prompted, then build the `app` module. Command line:

```powershell
.\gradlew.bat clean assembleDebug
```

Output:

```text
app\build\outputs\apk\debug\app-debug.apk
```

Install over the existing app with the same signing key to preserve the encrypted v9.1 session:

```powershell
adb install -r .\app\build\outputs\apk\debug\app-debug.apk
```

No backend, SQL or MT5 replacement is included.
