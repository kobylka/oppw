# OPPW repository instructions

These instructions apply to every task in this repository. They are mandatory for humans and coding agents.

## Context reset protocol

Before planning or editing, read in this order:

1. `VERSION`
2. `README.md`
3. `docs/CURRENT_ARCHITECTURE.md`
4. `docs/CONTRACT_POLICY.md`
5. `docs/CHANGE_CHECKLIST.md`
6. relevant architecture decisions in `docs/decisions/`
7. `git status --short`
8. the canonical implementation and its current tests

Repeat this protocol after context compaction, after inheriting work from another task, or whenever remembered details conflict with repository evidence. The repository is authoritative; chat history and release archives are not.

## Canonical source rules

- The project version exists only in root `VERSION` and uses `MAJOR.MINOR.PATCH`.
- The sole MT5 implementation is `mt5/oppw_mt5_continuous.py`.
- The sole committed MT5 config template is `mt5/oppw_mt5_config.example.py`.
- `mt5/oppw_mt5_continuous.py` is the sole MT5 entrypoint; account selection always uses `--account demo|real`.
- Files under `mt5/demo/` and `mt5/real/` are ignored private runtime/configuration files only. Do not add account launchers or copied strategy sources.
- Never create version-suffixed implementation copies, copied backend endpoints, patcher-generated backups, parallel installers, or source trees inside release folders.
- Tests must import the canonical implementation, never a historical copy.
- `dist/`, build outputs, IDE metadata, logs, state, locks, credentials, and local configuration are generated/runtime material and must remain untracked.

## Change discipline

- Keep each change set bounded and coherent. Do not assign a new release version until the complete validation gate passes.
- Inspect the working tree first and preserve unrelated user changes.
- Fix the canonical source in place. Do not solve merge uncertainty by making another copy.
- A defect fix requires a regression test that fails for the defect and exercises the current canonical source.
- An architectural change must update `docs/CURRENT_ARCHITECTURE.md` and add or supersede an Architecture Decision Record.
- A changed external or cross-component payload must follow `docs/CONTRACT_POLICY.md` and update producer, persistence, API, Android model/parser, fixtures, and tests together.
- Database changes are forward-only migrations registered once in `Mobile/backend/sql/migration-order.txt`. Never edit deployed history to disguise a new schema change.
- Keep one canonical endpoint per capability. Compatibility aliases require an explicit ADR, an expiry plan, and automated coverage.

## Trading-system safety

- Preserve execution ordering, idempotency, global lease/fencing checks, weekly-entry claims, and immutable audit links unless the user explicitly changes those requirements.
- Never live-test order submission, position modification, or market closure without explicit authorization.
- Dry-run, compilation, static checks, fixtures, and isolated tests do not authorize live trading.
- Any change affecting BUY, SELL, SL/TP, sizing, schedules, leverage, signal references, or exit hierarchy must update the canonical strategy specification payload and targeted tests.

## Required completion gate

Before declaring a change complete:

1. complete `docs/CHANGE_CHECKLIST.md` for the affected scope;
2. run `tools/validate_source.py`;
3. compile the canonical Python files and run all `mt5/tests`;
4. lint affected PHP;
5. validate the ordered migrations against disposable MySQL when SQL/backend persistence changed;
6. run Android unit tests and build when Android or its API contract changed;
7. run `tools/validate_contracts.py` when a cross-component contract changed;
8. run `git diff --check` and inspect the final staged/unstaged scope;
9. state any validation that could not run and the precise environmental reason.

Only `tools/release.ps1` may produce a release archive. It must run from a clean commit and must not be bypassed because a task is urgent.

## Clean-context principle

Do not rely on remembering these rules. If an important convention is not encoded in canonical documentation, a test, or a validator, add that enforcement as part of the change.
