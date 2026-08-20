# ADR 0037: Completed-session close candle authority

- Status: Accepted
- Date: 2026-08-20

## Context

MT5 timestamps an M1 candle by its opening instant, while an exchange calendar supplies the instant at which the session ends. An exact lookup at a 22:00 close therefore asks for a candle opening at the boundary instead of the final 21:59 candle ending there. Broker symbols with different after-hours schedules can return different results for that exact query. Independent close lookup paths caused leverage preview to recover a previous-week close while an enabled entry rule remained fail-closed until its bounded window expired.

## Decision

Use one canonical completed-session-close lookup for entry controls, leverage selection, daily-close processing, and recovery. It reads the account's configured MT5 symbol and selects the latest valid M1 candle whose opening timestamp is strictly before the exchange-calendar session-close boundary and within a bounded lookback. Cache successful results by symbol, session date, and boundary; do not cache misses, so a transient history failure can recover. Throttle structured missing-history diagnostics and retain the fail-closed entry policy.

Publisher snapshots and `strategy_market_points` remain monitoring data. They never replace the executor's broker-history input because they may come from a different process, terminal, node, symbol, or capture minute.

## Consequences

- A Bossa session closing at 22:00 uses the final 21:59 M1 candle.
- A broker candle opening at 22:00 is excluded from that completed cash session.
- Bossa and TMS retain independent symbol-specific broker history while sharing identical close-selection semantics.
- Missing inputs remain unable to authorize a BUY, but retries no longer create an unbounded warning storm and a missed-window record identifies the missing inputs.
