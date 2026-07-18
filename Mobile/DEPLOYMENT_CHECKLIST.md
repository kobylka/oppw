# OPPW Monitor Android v10 deployment checklist

1. Keep your existing `local.properties`, especially `sdk.dir` and `OPPW_API_BASE_URL`.
2. Replace the Android project with the v10 source or copy your `local.properties` into the v10 root.
3. Open the project in Android Studio with JDK 17.
4. Sync Gradle and build `app`.
5. Install over the existing `com.oppw.monitor` application where signing permits it.
6. Open Overview on Saturday with the carried Friday position and confirm:
   - `Market CLOSED`
   - phase `Weekend`
   - Next action `None`
   - no OH countdown
   - the position is still visible on Position.
7. Confirm the equity chart uses elapsed calendar time for horizontal spacing.
8. Confirm `Closest condition` is not repeated under `All other conditions`.
9. Open Analytics and confirm Sharpe/Sortino state that they use closed trades.
10. Open Logs and confirm routine checks are hidden before touching the switch; enable it and confirm they appear.

No SQL migration, backend upload, or MT5 replacement is part of this Android-only package.
