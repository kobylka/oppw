# ADR 0023: Secure token storage and verify build inputs

- Status: Accepted
- Date: 2026-07-30
- Extends: ADR 0001, ADR 0003, and ADR 0004

## Context

The Firebase OAuth cache used a predictable file in the shared system temporary directory. One paired-device read endpoint called an undefined authentication helper and passed strings to a typed timestamp formatter, producing an unauthenticated fatal path. Build inputs were also only partially reproducible: the Gradle distribution had no pinned hash, the committed wrapper JAR was not the official generated artifact, transitive Gradle artifacts had no verification metadata, and MT5 Python dependencies were unversioned.

The repository also contained a web-server example even though deployment used a different server configuration. That created an inaccurate assurance boundary: repository review could not establish which route and source-file restrictions were actually deployed.

## Decision

Firebase push requires an explicit private OAuth cache directory outside the web root. Shared temporary storage is not a fallback. The cache directory and file use locking, reject symlinks and non-regular files, and enforce owner-only POSIX permissions. Strategy-specification history uses the canonical paired-device session and account-grant checks and formats database timestamps through explicit UTC `DateTimeImmutable` values.

The Android build commits the official Gradle 9.4.1 generated wrapper JAR, pins the Gradle distribution SHA-256, and uses strict dependency verification metadata generated from both debug and release graphs. Wrapper bootstrap downloads the full pinned distribution, verifies it before execution, generates the wrapper with Gradle itself, and checks the generated JAR hash. Android Studio additionally resolves non-executable source and documentation attachments while importing Gradle models; verification metadata narrowly trusts files matching `*-sources.jar`, `*-javadoc.jar`, and the exact `gradle-9.4.1-src.zip`, while every executable plugin and dependency artifact remains checksum-verified. The Windows CPython 3.13 MT5 dependency graph is exact-version, binary-only, and SHA-256 locked in `requirements_mt5`.

No deployment-specific Apache, Nginx, or `.htaccess` configuration is canonical repository source. The actual deployment must independently enforce the HTTP endpoint allowlist and deny internal source material.

## Consequences

- Enabling push now requires a dedicated PHP-worker-owned cache directory; a missing or overly broad directory makes token acquisition fail instead of weakening storage.
- Strategy-specification history returns authenticated JSON instead of reaching an undefined function or timestamp type error.
- Dependency updates require deliberate lock/checksum review and regenerated Gradle verification metadata for debug and release graphs.
- IDE source/documentation browsing and Gradle synchronization work without adding hundreds of machine-generated attachment checksums or trusting executable JAR/AAR artifacts.
- Web-server exposure is validated against deployed configuration rather than inferred from an unused repository example.
