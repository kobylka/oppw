# Validation

Completed in the generation environment:

- All backend PHP files pass `php -l`.
- MT5 v34 and the credential-free example config pass Python bytecode compilation.
- All Android XML files parse successfully.
- Kotlin data models, sample data and formatting utilities compile with `kotlinc`.
- Backend model/parser field checks are consistent for market statistics, position data and analytics.
- MT5 AST comparison against v33 shows only `MobilePublisher.send` and `OPPWContinuousStrategy.monitor_all_conditions` changed.
- The `send` change is only the mobile publisher User-Agent.
- The `monitor_all_conditions` change only unifies the displayed CH target with the displayed OH target.
- No trading, sizing, protection, session, recovery, order or continuous-loop method changed.
- No private MT5, MySQL, API or Firebase service-account credential is included.

A complete Android Gradle build requires an Android SDK and external Android/Firebase dependencies and must be run in Android Studio or on the deployment computer.
