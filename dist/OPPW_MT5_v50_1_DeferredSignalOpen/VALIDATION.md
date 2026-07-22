# v50.1 validation

Completed locally:

- Python syntax compilation for generic, Demo, Real, and versioned v50.1 loops.
- Four focused deferred-signal tests:
  - early fill is never used as the break-even signal reference;
  - no bar lookup occurs before cash open;
  - exact cash-open capture is persisted when it becomes available;
  - non-final CH/BE waits, while final-week TO remains unconditional.
- All seven v50 session-indexed TPP and PRE H tests remain green.
- Full MT5 test suite: 37 tests passed.
- Installer copied and hash-verified all actual generic, Demo, and Real runtime paths.
- Runtime copies are byte-identical.
- `git diff --check` passed.

Not performed:

- live MT5 early BUY;
- live 15:30 cash-open capture;
- production backend publication.
