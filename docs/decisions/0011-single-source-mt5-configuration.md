# ADR 0011: Single-source MT5 configuration

- Status: Accepted
- Date: 2026-07-27
- Supersedes: the copied private-configuration format described by ADR 0005

## Context

Demo and Real private configuration files each copied the complete MT5 `Config` dataclass, its defaults, and environment parsing. A setting change therefore required synchronized edits to canonical code, the committed example, and both ignored private files. Drift was difficult to detect because private files are intentionally absent from Git, and replacing a template risked overwriting credentials.

## Decision

`mt5/oppw_core/settings.py` is the only authority for the frozen `Config` schema and canonical defaults. The ignored Demo and Real files contain exactly five required private constants—terminal path, login, password, server, and monitor write token—plus an optional `OVERRIDES` mapping of canonical field names.

The loader applies configuration in this fixed order:

1. canonical defaults and account-rooted runtime paths;
2. private account constants and explicit overrides;
3. `OPPW_*` environment variables;
4. explicit CLI runtime flags.

Unknown override names, duplicate credential definitions, or a private `Config` class fail startup. Startup emits the complete effective non-secret configuration so operators can diagnose precedence without exposing passwords or tokens.

`tools/migrate_mt5_config.py` is the only supported conversion path for legacy private files. It reads them with `OPPW_*` variables suppressed, writes a temporary override-only candidate, rebuilds the canonical configuration, compares every field, and atomically replaces the original only after exact equality succeeds. It creates no backup copy containing secrets.

## Consequences

- Adding or changing a default requires one canonical edit and corresponding tests.
- Private credentials survive upgrades without copying application code.
- Demo and Real may still differ deliberately through validated overrides.
- Environment and CLI deployment behavior remains compatible and has explicit precedence.
- Source validation rejects future copied configuration schemas and release packaging includes the migration utility.
