# ADR 0032: Named multi-account MT5 runtime

- Status: Accepted
- Date: 2026-08-13
- Supersedes: the fixed two-account filename/count portions of ADRs 0005, 0006, 0009, and 0011

## Context

The canonical runtime could distinguish only the fixed `DEMO` and `REAL` identities. Each environment had one private configuration file, and the Windows supervisor always managed exactly four children. Running a second Demo or Real login therefore required an unsupported copied launcher/configuration scheme or caused multiple broker accounts to share backend leases, weekly claims, runtime files, and audit identity.

## Decision

Keep `mt5/oppw_mt5_continuous.py` as the only MT5 entrypoint and separate two concepts:

- `--account demo|real` selects the account type and private-configuration directory;
- `--account-key ACCOUNT_KEY` selects the stable backend, coordination, audit, and runtime identity.

The account key defaults to `DEMO` or `REAL`, preserving existing commands. A named account uses one ignored override-only file in its type directory. `DEMO_ALPHA` loads `mt5/demo/demo_alpha_mt5_config.py`; `REAL_PROP` loads `mt5/real/real_prop_mt5_config.py`. Every file retains the five private credential constants and optional validated `OVERRIDES`; canonical defaults remain solely in `oppw_core/settings.py`. State, monitor history, and logs are scoped by account key. Strategy-relevant resolved differences produce the existing immutable per-account strategy specification.

The Windows service configuration contains an explicit ordered `managedAccounts` list of one to eight unique `{accountKey, accountType}` items. Both master and backup must use the same list, and every enabled backend account must match it. Startup remains globally serialized: all configured executors are attempted in configured account order, followed by all publishers in the same order. Readiness, failure backoff, assignments, leases, fencing, weekly claims, and desired state remain keyed by the stable account key.

`Mobile/backend/admin/register_account.php` is the canonical CLI operation for registering or re-enabling a named account in existing multi-account tables. No schema change is required. Each broker login must use its own MetaTrader installation/terminal path so concurrent initialization cannot switch another account's terminal session.

## Consequences

- Multiple Demo and multiple Real accounts can run the same canonical strategy with independent credentials and `OVERRIDES`.
- Existing `DEMO` and `REAL` files, commands, backend identities, and Mobile behavior remain compatible.
- Account keys cannot contain spaces or path characters and cannot be duplicated across Demo and Real; the legacy keys `DEMO` and `REAL` are reserved for their matching types.
- Supervisor/backend account-list drift fails closed instead of silently leaving an enabled account unmanaged.
- Adding an account is an explicit deployment operation on both nodes and in the backend; copying strategy code or adding launchers remains prohibited.
