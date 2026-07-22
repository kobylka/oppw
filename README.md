# OPPW

OPPW has one canonical source tree and one project version.

## Canonical files

- `VERSION` is the only release version.
- `mt5/oppw_mt5_continuous.py` is the only MT5 loop implementation.
- `mt5/oppw_mt5_config.example.py` is the only committed MT5 configuration template.
- `Mobile/` contains the Android application and PHP/MySQL backend.
- `Mobile/backend/sql/migration-order.txt` defines the database migration order.

The files under `mt5/demo/` and `mt5/real/` are compatibility launchers. They execute the canonical loop and do not contain strategy code. Private account configuration files remain local and ignored by Git.

## Validate and release

Run the only supported release command from a clean commit:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release.ps1 -RepoRoot D:\oppw
```

The command refuses a dirty repository, validates source-layout invariants, compiles and tests the MT5 loop, lints PHP, applies the complete SQL migration chain to temporary MySQL, builds and tests Android, and creates a checksummed archive in `dist/`.

Generated archives, IDE files, runtime state, local credentials, account logs, and historical source copies are not committed.

Every change begins with [AGENTS.md](AGENTS.md). Current system ownership and boundaries are documented in [docs/CURRENT_ARCHITECTURE.md](docs/CURRENT_ARCHITECTURE.md), with contract rules in [docs/CONTRACT_POLICY.md](docs/CONTRACT_POLICY.md) and the required checklist in [docs/CHANGE_CHECKLIST.md](docs/CHANGE_CHECKLIST.md).

Release details are in [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md), and strategy authority is described in [docs/STRATEGY_SPECIFICATION.md](docs/STRATEGY_SPECIFICATION.md).
