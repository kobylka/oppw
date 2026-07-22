# ADR 0007: Independent Android application version

- Status: Accepted
- Date: 2026-07-22
- Supersedes: the Android version derivation described by ADR 0001 and prior release documentation

## Context

The product release line has advanced to 52.x while the Android application must continue as an independently managed 16.x line. Deriving Android `versionName` from root `VERSION` prevents that identity. Simply changing the old product-derived Android `versionCode` from 520001 to 160000 would also make Android treat the new build as a downgrade.

## Decision

Root `VERSION` remains the canonical product/MT5/backend/service release and archive identity. `Mobile/VERSION` is the sole canonical Android application version and uses `MAJOR.MINOR.PATCH`.

Android derives `versionName` directly from `Mobile/VERSION` and derives a monotonic integer code as:

```text
versionCode = 1,000,000 + major * 10,000 + minor * 100 + patch
```

The minor and patch components are each restricted to 0 through 99. For mobile 16.0.0 this produces version code 1,160,000, above all historical product-derived Android codes through product 99.99.99. Repository validation enforces both canonical version files and the Android derivation. Release packaging includes both files, while the outer archive continues to use root `VERSION`.

## Consequences

Android can advance independently without changing MT5, backend, service, strategy specification, or archive identity. Mobile release tooling must bump `Mobile/VERSION`, and product release tooling must bump root `VERSION`; a coordinated release may bump both. Cross-component compatibility continues to be governed by `docs/CONTRACT_POLICY.md`, not by assuming equal version numbers.
