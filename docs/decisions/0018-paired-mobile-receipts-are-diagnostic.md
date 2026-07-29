# ADR 0018: Paired mobile receipts are diagnostic

- Status: Accepted
- Date: 2026-07-29

## Context

Paired mobile devices are monitoring principals. They may have an explicit grant to change supervised-service desired state, but they are not publishers and must not be able to create strategy specifications, decisions, execution stages, fills, protection changes, or trade transitions. The mobile delivery acknowledgement previously called the shared execution-authority writer and could therefore insert a forged `MOBILE_RECEIPT` row into `strategy_execution_stages`.

## Decision

`mobile-receipt.php` writes a fixed-name `MOBILE_RECEIPT` diagnostic event only. Analytics may merge that diagnostic into delivery-latency presentation, but the receipt never enters an immutable strategy-authority table and never supplies broker or trading facts. Executable contract validation asserts both sides of this boundary: the receipt remains visible in latency analytics and creates no authority stage.

Paired-device credentials remain unable to write strategy authority. Their other writes are limited to device-owned authentication/push metadata, unpairing, and the separately granted service-control capability.

## Consequences

- A compromised paired monitor cannot forge an immutable execution stage.
- Delivery latency remains observable but has diagnostic retention and trust semantics.
- Historical authority rows are not rewritten; the corrected boundary applies to new receipts.
- Any future mobile-originated observation must use a monitor-owned or diagnostic store unless a new ADR explicitly changes the authority model.
