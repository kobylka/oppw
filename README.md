# OPPW

OPPW has one canonical source tree with independently versioned product and Android release lines.

## Canonical files

- `VERSION` is the product/MT5/backend/service release version and archive identity.
- `Mobile/VERSION` is the Android application release version.
- `mt5/oppw_mt5_continuous.py` is the only MT5 loop implementation.
- `mt5/oppw_mt5_config.example.py` is the only committed MT5 configuration template.
- `Mobile/` contains the Android application and PHP/MySQL backend.
- `service/` contains the canonical two-node Windows service supervisor and installer.
- `Mobile/backend/sql/migration-order.txt` defines the database migration order.

Run the canonical entrypoint directly and select the account explicitly:

```powershell
python .\mt5\oppw_mt5_continuous.py --account demo
python .\mt5\oppw_mt5_continuous.py --account real
```

Private account configuration files remain local and ignored as `mt5/demo/demo_mt5_config.py` and `mt5/real/real_mt5_config.py`.

Install the continuous supervisor from elevated PowerShell with `service/install-service.ps1`. Use `-NodeRole Master` on the preferred machine and `-NodeRole Backup` on the standby machine. Both services stay online; backend assignment and the existing global leases decide which node may run each account/role.

## Validate and release

Run the only supported release command from a clean commit:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\release.ps1 -RepoRoot D:\oppw
```

The command refuses a dirty repository, validates source-layout invariants, compiles and tests the MT5 loop, lints PHP, applies the complete SQL migration chain to temporary MySQL, runs the executable PHP/MySQL/API-to-Android contract, builds and tests Android, and creates a checksummed archive in `dist/`.

Generated archives, IDE files, runtime state, local credentials, account logs, and historical source copies are not committed.

Every change begins with [AGENTS.md](AGENTS.md). Current system ownership and boundaries are documented in [docs/CURRENT_ARCHITECTURE.md](docs/CURRENT_ARCHITECTURE.md), with contract rules in [docs/CONTRACT_POLICY.md](docs/CONTRACT_POLICY.md) and the required checklist in [docs/CHANGE_CHECKLIST.md](docs/CHANGE_CHECKLIST.md).

Release details are in [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md), and strategy authority is described in [docs/STRATEGY_SPECIFICATION.md](docs/STRATEGY_SPECIFICATION.md).
