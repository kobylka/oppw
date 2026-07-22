## Scope

Describe the bounded change and the canonical files modified.

## Contract impact

- [ ] No cross-component contract change
- [ ] Producer, PHP, MySQL, read API, Android model/parser/UI and fixtures were updated atomically
- [ ] Migration added to `Mobile/backend/sql/migration-order.txt`

## Architecture and safety

- [ ] Read and followed `AGENTS.md`
- [ ] No versioned source copies, duplicate endpoints, backup files or parallel installers added
- [ ] Trading behavior is unchanged, or the intended strategy/execution change is documented and tested
- [ ] `CURRENT_ARCHITECTURE.md` and an ADR were updated when required
- [ ] No credentials, runtime state or generated artifacts are tracked

## Validation

- [ ] `tools/validate_source.py`
- [ ] Python compilation and complete `mt5/tests`
- [ ] PHP lint/JSON validation where applicable
- [ ] Disposable-MySQL migration validation where applicable
- [ ] Android tests/build where applicable
- [ ] `git diff --check`

List any check that could not run and why.
