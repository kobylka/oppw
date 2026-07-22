# ADR 0005: Single MT5 entrypoint and explicit account configuration

- Status: Accepted
- Date: 2026-07-22
- Supersedes: the account-launcher portion of ADR 0001

## Context

The Demo and Real directories contained identically named compatibility launchers. They held no strategy logic, but their filenames looked like duplicated implementations and preserved multiple ways to start the same program. Configuration loading also accepted historical filename aliases, which made the effective private configuration less obvious.

## Decision

`mt5/oppw_mt5_continuous.py` is the only implementation and the only executable entrypoint. Every process selects its account with `--account demo|real` and its role with `--mode executor|publisher`.

The selected account has exactly one private configuration filename:

- Demo: `mt5/demo/demo_mt5_config.py`
- Real: `mt5/real/real_mt5_config.py`

There are no account-specific launchers, copied loops, root-level configuration fallbacks, or historical configuration aliases.

## Consequences

- Commands and process supervisors must call the canonical entrypoint.
- A missing account-specific configuration fails explicitly with its exact expected path.
- Releases contain one MT5 Python implementation and one credential-free configuration template.
- Source validation rejects any additional `oppw_mt5_continuous.py` entrypoint or reintroduced configuration fallback.
