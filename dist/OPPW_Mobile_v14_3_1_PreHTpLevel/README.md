# OPPW Monitor v14.3.1 — PRE H potential TP level

The Position screen now shows the exact live interpolated PRE H percentage:

```text
PRE H
Target price: 29,xxx.xx
Distance: ...
Current potential TP level: 1.37%
```

The percentage is supplied by MT5 v50 as `potentialTpPercent` and changes with
the ramp. Cached/older snapshots remain compatible because the field is
nullable.

Android version:

```text
versionName = 14.3.1
versionCode = 31
```

## Install source

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\install_mobile_v14_3_1.ps1 `
  -RepoRoot D:\oppw
```

Build:

```powershell
cd D:\oppw\Mobile
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug
```

Or install the included debug APK:

```powershell
adb install -r .\OPPWMonitor-v14.3.1-debug.apk
```

No backend or database change is required. The running publisher/executor must
use the updated v50 loop so the new percentage is present in snapshots.

