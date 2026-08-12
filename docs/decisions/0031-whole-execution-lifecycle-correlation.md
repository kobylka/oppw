# ADR 0031: Correlate and filter whole execution lifecycles

- Status: Accepted
- Date: 2026-08-12
- Extends: ADR 0003, ADR 0024, and ADR 0030

## Context

MT5 does not provide the eventual position ticket before an entry order is accepted and becomes visible. Consequently `SIGNAL`, `DECISION`, `CHECKED`, `SENT`, `ACCEPTED`, and an immediate `FILLED` can legitimately carry ticket `0`, while `POSITION_VISIBLE` and subsequent stages carry the definitive ticket. Analytics applied trade filters independently to every stage, hiding the early portion of an otherwise complete execution.

The mutable trade projection could also replace its entry-decision link with a later flat-account what-if decision because the snapshot decision was preferred over the execution decision and the link was updated repeatedly. This made the filtering defect visible for DEMO ticket 2184944 even though its early immutable stages were present.

A broker-triggered BH TP closes at the broker without an executor market-SELL request. Presenting its absent `EXIT_CHECKED` and `EXIT_SENT` as missing execution work is misleading.

## Decision

Analytics groups every stage by execution identity before applying decision/ticket filters. Any definitive ticket or matching decision within the group includes the complete lifecycle, including earlier ticket-zero stages. The first non-empty execution decision and first positive position ticket are the lifecycle's presentation identity.

The executor binds a new execution explicitly to the latest authoritative strategy decision immediately before `SIGNAL`. Subsequent decision calculations do not mutate an existing execution identity. Backend trade linking prefers `snapshot.execution.decisionId`, fills projection metadata only when absent, and never replaces an established entry link. A forward-only migration repairs mutable historical projections from their earliest `POSITION_VISIBLE` stage; immutable stages and decisions are unchanged.

Android includes `EXIT_FILLED` in the lifecycle and labels absent executor market-exit request stages as `N/A · broker-managed exit` when a position closed without those stages.

## Consequences

- Ticket-filtered analytics show the complete entry lifecycle.
- Trade decision links remain tied to entry authorization.
- Existing affected projections are repaired without mutating immutable authority.
- Broker SL/TP exits remain truthful and do not acquire fabricated market-order stages.
- This behavior starts with product release 56.2.0 and Android release 17.3.0.
