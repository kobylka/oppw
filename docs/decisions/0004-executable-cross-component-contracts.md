# ADR 0004: Executable cross-component contracts

Status: Accepted
Date: 2026-07-22

## Context

The Python, PHP, SQL, and Android layers previously had useful component tests, but those tests could all pass while the components disagreed about a field name, unit, identifier, persistence rule, or response shape. This was a recurring source of regressions during rapid changes.

## Decision

The release gate runs a representative contract through the actual stack:

```text
contract fixture
  -> canonical PHP coordination and ingest endpoints
  -> ordered schema and migrations in disposable MySQL
  -> canonical status and analytics endpoints
  -> production Android JsonParser and models
```

`contracts/` owns representative input and expected semantics. `tools/validate_contracts.py` owns orchestration. It must exercise authentication, global publisher fencing, repeated-delivery idempotency, immutable authority rows, JSON errors, status projection, analytics lifecycle reconstruction, mobile receipt latency, and parsing of the exact API responses by Android.

The validator uses only disposable credentials, a temporary PHP configuration, a localhost-only database port, and an automatically removed MySQL container. It must never connect to production MySQL or submit an MT5 order.

## Consequences

- A cross-component mismatch stops `tools/release.ps1` before an archive is produced.
- Contract fixtures and expectations are canonical source, not generated release evidence.
- Normal component tests remain valuable and run in addition to this gate.
- Contract changes must update the fixture, producer/persistence/API/Android layers, and assertions together.
- Docker, PHP with PDO MySQL, JDK 17, and the Android toolchain are release prerequisites.
