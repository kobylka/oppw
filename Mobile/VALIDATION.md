# v10.1 validation

Completed in the packaging environment:

- The four requested authentication/data files are byte-for-byte identical to the supplied v9.1 source files.
- `JsonParser.parseAuthSession()` retains the v9.1 nested-session format.
- No reconstructed `ApiClient.kt`, `SessionStore.kt`, static bearer-token client or biometric code exists.
- Android manifest and every XML resource parse successfully.
- Pure Kotlin models and closed-trade calculations compile and execute successfully.
- Closed-trade Sharpe/Sortino behavior was exercised with five returns.
- The project contains no import of Compose's internal `RowColumnParentData.weight` property.
- Kotlin delimiter/string checks pass.
- ZIP integrity and source checksums are generated during packaging.

A full Android Gradle build was not possible in this container because Gradle/Maven network access and an Android SDK are unavailable. The project uses the same Gradle, AGP, Kotlin, Compose and SDK versions as the working v9.1 source.
