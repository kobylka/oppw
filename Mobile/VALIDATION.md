# Validation

Completed in the generation environment:

- All PHP files pass `php -l`.
- MT5 v33 and config pass Python bytecode compilation.
- Kotlin data models and sample data compile with `kotlinc`.
- MT5 AST comparison shows only these strategy-class methods changed from v32:
  - `monitor_tick_snapshot`
  - `monitor_next_action`
  - `monitor_all_conditions`
  - `monitor_closest_condition`
  - `build_mobile_snapshot`
- No trading, sizing, protection, session, recovery or order method changed.

A complete Android Gradle build requires an Android SDK and must be run in Android Studio or on the deployment computer.
