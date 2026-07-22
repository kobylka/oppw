# Change and release checklist

Use the applicable items for every change. The release validator confirms that this checklist and the governing documents remain present; the person or agent completing a task must report skipped environmental checks explicitly.

## Before editing

- [ ] Read `AGENTS.md` and complete its context reset protocol.
- [ ] Inspect `git status --short` and preserve unrelated changes.
- [ ] Identify the canonical source and existing tests.
- [ ] Identify every producer, persistence, API, model, parser, UI, and deployment consumer affected.

## Implementation

- [ ] Modify canonical sources only—no versioned copies, backup files, endpoint aliases, or parallel installers.
- [ ] Keep strategy behavior unchanged unless the request explicitly changes it.
- [ ] Add a focused regression test for every defect fixed.
- [ ] Apply cross-component changes atomically under `CONTRACT_POLICY.md`.
- [ ] Register every new SQL migration in `migration-order.txt`.
- [ ] Update `CURRENT_ARCHITECTURE.md` and add/supersede an ADR for architectural changes.
- [ ] Keep secrets, runtime state, logs, caches, IDE files, and generated artifacts untracked.

## Validation

- [ ] Run canonical source validation.
- [ ] Compile Python and run the complete MT5 test suite.
- [ ] Lint affected PHP and confirm JSON endpoints return JSON on failure.
- [ ] Apply the ordered schema/migrations to disposable MySQL when persistence is affected.
- [ ] Run Android unit tests and build when Android or its contract is affected.
- [ ] Compile the Windows service host and run supervisor tests when service supervision is affected.
- [ ] Run the executable PHP/MySQL/API/Android contract when any cross-component contract is affected.
- [ ] Run `git diff --check`.
- [ ] Inspect the final diff and confirm no unrelated files or credentials are included.

## Release and deployment

- [ ] Change only root `VERSION` for release identity.
- [ ] Commit the coherent change set; release only from a clean commit.
- [ ] Run `tools/release.ps1`; do not hand-assemble a release ZIP.
- [ ] Verify archive and per-file checksums.
- [ ] Apply migrations before code that requires them.
- [ ] Verify deployed build ID, endpoint health, and account/role selection.
- [ ] Record validation limitations and rollback considerations.
