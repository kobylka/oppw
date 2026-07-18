# OPPW Monitor Android v11

Complete Android Studio project based on v10.1.1. The application remains read-only and contains no trading controls.

## v11

When the selected account is flat, the Position screen now displays the next potential trade published by MT5 loop v41 or newer:

- side and symbol;
- potential volume;
- current MT5 price used for sizing;
- required margin deposit;
- account balance used for sizing;
- chosen strategy leverage, normally 8x or 10x;
- the exact reason for choosing 8x or 10x;
- effective leverage calculated as `required deposit / balance`;
- potential notional and sizing units when supplied.

When MT5 cannot calculate the preview, the Position screen displays the publisher error and still shows the selected leverage and leverage reason when available. When the backend has not received a `potentialPosition` object, the screen explicitly states that MT5 v41 or newer is required.

An open position continues to use the existing Position screen unchanged.

## Required MT5 payload

MT5 v41 publishes this object inside `snapshot` while flat:

```json
{
  "potentialPosition": {
    "available": true,
    "symbol": "US100",
    "side": "BUY",
    "price": 28750.0,
    "volume": 0.01,
    "requiredDeposit": 2180.0,
    "balance": 28200.0,
    "effectiveLeverage": 0.0773049645,
    "strategyLeverage": 8.0,
    "leverageReason": "8x because previous full-week change -1.2000% >= -2.5000% and previous trade change -0.3000% >= -0.7000%",
    "positionNotional": 28750.0,
    "sizingUnits": 1,
    "error": ""
  }
}
```

The parser accepts both camelCase and snake_case variants. The app recalculates effective leverage from required deposit and balance, using the publisher value only as a fallback.

## Authentication

The v9.1 authentication implementation remains unchanged:

```text
app/src/main/java/com/oppw/monitor/auth/AuthModels.kt
app/src/main/java/com/oppw/monitor/auth/SecureSessionStore.kt
app/src/main/java/com/oppw/monitor/data/StatusApiClient.kt
app/src/main/java/com/oppw/monitor/data/StatusRepository.kt
```

Pairing continues to read the nested `session` object returned by `auth/pair.php`. Existing paired sessions remain encrypted with Android Keystore.

## Existing retained behavior

- Weekend action suppression for a position left open after Friday.
- Time-scaled equity curves.
- Closest-condition de-duplication.
- Closed-trade Sharpe and Sortino.
- Routine-log filtering without blank rows.
- Existing account selection, notifications, Firebase integration, refresh-token rotation and unpairing.

## Configure and build

Preserve your existing `local.properties`, or copy `local.properties.example` and set:

```properties
OPPW_API_BASE_URL=https://your-domain.example/oppw-backend/
```

Build with Android Studio/JDK 17 and Android SDK 37:

```powershell
cd D:\oppw\Mobile
.\gradlew.bat clean assembleDebug
```

Install over the existing app with the same signing key to preserve pairing:

```powershell
adb install -r .\app\build\outputs\apk\debug\app-debug.apk
```

Version name: `11.0.0`  
Version code: `15`  
Application ID: `com.oppw.monitor`
