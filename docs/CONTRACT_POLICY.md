# Cross-component contract and versioning policy

## Scope

This policy applies whenever data crosses any boundary:

```text
MT5 loop → PHP ingestion → MySQL → PHP read API → Android parser/model/UI
```

It also applies to coordination leases, execution lifecycle records, strategy specifications, decisions, trades, fills, protection changes, cash flows, status, analytics, and authentication responses.
Windows supervisor heartbeats, assignments, mobile desired-state commands, and account control permissions are included in this policy.

## Atomic contract change rule

A contract change is one change set. Update every affected layer together:

1. producer field and semantics;
2. ingestion validation and persistence;
3. forward-only SQL migration and migration order when storage changes;
4. read endpoint response;
5. Android model and parser;
6. UI behavior;
7. representative fixture and regression tests;
8. `docs/CURRENT_ARCHITECTURE.md` if ownership or topology changes.

Do not deploy a producer-only or consumer-only change that requires the other side to guess.

## Compatibility rules

- Additive optional fields are preferred.
- Existing field meaning, units, time zone, sign, and nullability must not change silently.
- Renaming uses a documented transition: producer emits the canonical name, consumer may temporarily read the old name, and removal is tracked by an ADR.
- A field that becomes required needs a staged rollout or explicit contract-version transition.
- Timestamps must be ISO-8601 with an offset unless the documented field is an epoch value.
- Percent values must state whether they are ratios (`-0.005`) or percentage points (`-0.5`).
- Identifiers must retain stable scope and idempotency semantics.
- Errors from JSON endpoints must remain JSON; PHP warnings must never become HTML response prefixes.

## Persistence rules

- Immutable business records use deterministic IDs and payload/specification hashes.
- Repeated identical delivery is idempotent.
- Reusing an ID with different authoritative content is an error.
- Diagnostic events may describe an operation but do not substitute for its authoritative row.
- Projections used by mobile screens must identify their authoritative inputs.

## Endpoint rules

- One canonical endpoint owns each capability.
- Do not add filename aliases as a quick compatibility fix.
- A necessary alias requires an ADR naming its owner, callers, removal condition, and expiry release.
- Authentication behavior is consistent across read endpoints; analytics does not invent a separate token.

## Required tests

For an affected contract, test at least:

- representative success payload;
- missing optional values;
- invalid or mismatched authoritative identifiers;
- repeated delivery/idempotency;
- JSON response validity;
- Android parsing of the actual endpoint shape;
- timestamp and numeric-unit semantics;
- historical compatibility when promised.

Contract validation belongs in the canonical test/release gate. A manual app refresh is supporting evidence, not the only test.

The mandatory executable contract is defined by `contracts/` and orchestrated by `tools/validate_contracts.py`. It persists a representative publisher payload through the real PHP endpoints and ordered MySQL schema, reads it through the real status and analytics endpoints, and passes those exact JSON responses to the production Android `JsonParser`. Component mocks do not replace this test.

## Versioning

Root `VERSION` is the product release version. Do not add independent source-file version labels. A breaking external contract requires a deliberate major-version decision and an ADR; ordinary compatible evolution uses the normal project version and migrations.
