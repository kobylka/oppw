# ADR 0030: Exact broker-protection close reconciliation

- Status: Accepted
- Date: 2026-08-12
- Supersedes: ADR 0024's installed-protection fallback for broker-side closes

## Context

A disappeared DEMO position had both a hard SL and a BH TP installed. The loop independently preferred the BH reason and the hard-SL price, producing an impossible `BH` close at the SL and a false −6.2472% previous-trade return. The actual broker close was the BH TP near −0.4%.

## Decision

When a managed long position disappears, the executor queries completed MT5 deal history by position identifier and requires the latest exact SELL deal before clearing position state. `DEAL_REASON_TP` selects the active TP reason and `DEAL_REASON_SL` selects the active SL reason. The executor publishes the deal ticket, actual fill price, filled volume, and exact deal timestamp through `EXIT_FILLED`, followed by the matching `CLOSED` lifecycle stage.

If the exact deal is temporarily unavailable, reconciliation remains pending, position-scoped state remains intact, and the executor does not proceed to another entry. The installed-protection fallback keeps each reason paired with its own price for diagnostics, but it is not allowed to finalize a disappeared position.

The Android current-week card displays the actual open position price when one exists. It displays the cash-week open only while flat; weekly market percentages continue to use the cash-week open as their calculation reference.

An execution stage's explicit `details.event_at` is the authority timestamp for execution, fill, protection, projection, and compatibility-event persistence; the surrounding log-envelope time is only a fallback. A market exit deal already published from its order acknowledgement is remembered in durable strategy state so disappearance reconciliation does not emit a duplicate `EXIT_FILLED` for the same MT5 deal ticket.

This behavior begins with product release 56.1.0 and Android release 17.2.0.

## Consequences

- Broker SL/TP closes use actual MT5 deal price, reason, and time.
- Exact deal publication is idempotent across immediate market acknowledgements and later position-disappearance reconciliation.
- A flat publisher snapshot can still create a provisional non-exact projection, but the executor's exact fill repairs it.
- Temporary MT5 history failure blocks new entry rather than contaminating leverage and arithmetic-loss inputs.
- Position open and week open remain distinct values in the Mobile presentation.
