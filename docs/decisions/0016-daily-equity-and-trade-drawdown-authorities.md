# ADR 0016: Daily-equity and trade-drawdown authorities

- Status: Accepted
- Date: 2026-07-28
- Supersedes: ADR 0014 and ADR 0015

## Context

Treating every retained minute as a portfolio drawdown point created hundreds of short episodes over long analytics windows and allowed intraday highs to establish peaks that were inconsistent with a daily-equity chart. Returning only minute episodes longer than 24 hours reduced payload size but did not restore the intended distinction between portfolio risk metrics and the closed-trade episode list.

Daily closes alone are also insufficient because a position can suffer a material unrealized loss and recover before the close. Closed-trade episodes need those minute observations for their real trough and timing, but minute fluctuations must not define which closed-trade drawdowns exist.

## Decision

Portfolio drawdown metrics and the chart use a cash-flow-adjusted daily curve. For every Warsaw weekday with hot minute history, the curve retains the first point, the lowest minute-equity point, and the closing point in timestamp order. This makes daily peaks and recoveries authoritative while preserving the true intraday low. Daily fallback supplies the retained close when minute history is unavailable.

The episode list uses a separate closed-trade authority. Compounded closed-trade account returns define each episode's identity, member trades, recovery trade, and ongoing state. Its starting timestamp is the opening of the first trade whose close puts the compounded curve below its peak. If that trade overlaps the preceding peak-setting close, the later peak timestamp is used so the interval remains ordered. This excludes flat time between the preceding profitable close and the next exposure. During the same streaming equity scan, minute equity within the trade-defined interval refines the starting equity value, trough timestamp, and depth without replacing the trade-defined starting timestamp. A recovered episode still ends at the recovering trade close; an ongoing episode extends to the latest available equity point. Elapsed and trough-to-recovery durations therefore use the exposure and minute timing without allowing minute noise or retention gaps to redefine episodes.

The analytics rolling window is anchored to the latest trade or equity observation in the selected account scope, whichever is later. Trade inactivity must not truncate newer minute equity from an ongoing episode.

Only trade-defined episodes with elapsed duration of at least 86,400 seconds are transferred. `episodeCount` reports all trade-defined episodes, `episodeMinimumSeconds` reports the threshold, and `episodeAuthority` identifies the hybrid authority. The Android app labels the chart and episode list separately and retains the longer analytics read timeout.

## Consequences

- Portfolio risk metrics remain daily while including unrealized intraday lows.
- Intraday highs and repeated minute oscillations no longer create hundreds of portfolio episodes.
- Episode cards correspond to closed-trade drawdowns, with minute-accurate troughs and timing.
- Ongoing episodes include equity weeks newer than the most recent trade record.
- Trade-only filters affect the episode list without claiming to reconstruct a filtered account-equity curve.
- Older retained history has daily-close precision and cannot refine a trough after minute retention expires.
