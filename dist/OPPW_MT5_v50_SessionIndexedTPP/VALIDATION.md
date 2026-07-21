# v50 validation

Completed locally:

- Python syntax compilation of the generic, Demo, Real, and versioned v50 loops.
- Seven focused unit tests:
  - unchanged normal-week TPP schedule;
  - Tuesday-first full-week TPP shift;
  - normal Tuesday PRE H ramp boundaries;
  - Tuesday-first Wednesday PRE H ramp boundaries;
  - no PRE H ramp on an ordinary Wednesday;
  - crossed PRE H threshold calls market close with reason `PRE H`;
  - mobile condition payload includes the exact current potential TP percentage.
- Static scan confirmed all runtime TPP selection routes through the centralized
  session-indexed schedule. The only direct TPP indices are the explicit first
  and second values used as PRE H interpolation endpoints.
- AST comparison against v49.2 confirmed that only the three new scheduling
  helpers and the nine execution/status/logging consumers required for this
  feature changed; no other strategy method changed.
- Installer executed successfully against `D:\oppw` and verified all installed
  runtime hashes.
- `git diff --check` passed for the implementation.

Not performed:

- live MT5 order submission;
- production broker execution;
- production backend publication.
