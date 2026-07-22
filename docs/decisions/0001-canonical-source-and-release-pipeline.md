# ADR 0001: Canonical source and reproducible release pipeline

- Status: Accepted; account-launcher portion superseded by ADR 0005; Android version scope clarified by ADR 0007
- Date: 2026-07-22

## Context

Repeated version-suffixed Python files, copied account loops, generated source trees, one-off installers, and release archives in Git caused fixes to land in stale files and made deployed versions ambiguous.

## Decision

Maintain one MT5 implementation, one configuration template, and one root product version. Account entrypoints are thin launchers. Generated releases live only in ignored `dist/`. `tools/release.ps1` is the sole packaging path and refuses a dirty repository.

## Consequences

Tests and deployments always exercise the same implementation. Historical releases remain available through Git history and published artifacts rather than active source copies. Urgent changes must still pass the gate.
