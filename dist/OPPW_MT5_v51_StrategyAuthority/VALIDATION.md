# v51 validation

Completed locally:

- Python syntax compilation;
- 43 MT5 regression tests passed;
- canonical specification hash determinism and completeness;
- immutable decision/spec linkage;
- lifecycle records include specification, order, deal, side, and volume fields;
- both snapshot and event-only ingestion call normalized authority persistence;
- deterministic identifiers make retransmission idempotent;
- SQL contains every authority table and update/delete rejection trigger;
- source copies are byte-identical;
- Git whitespace validation passed.

Not performed locally:

- production MySQL migration;
- live PHP request against production;
- live MT5 order submission.

No PHP executable was available in this workspace, so PHP files received static delimiter/structure checks rather than `php -l`. Run `php -l` on every packaged backend file before upload.
