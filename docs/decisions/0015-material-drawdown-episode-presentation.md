# ADR 0015: Material drawdown episode presentation

- Status: Superseded by ADR 0016
- Date: 2026-07-28

## Context

An 80-week analytics request can examine hundreds of thousands of minute-equity samples. The chart series was already bounded, but the backend retained and transferred every drawdown episode. Frequent short movements could therefore create an unbounded episode list and contribute to Android exceeding its general 8-second read timeout even though those movements were not useful as individual cards.

Filtering episodes before aggregate calculation would make average depth, average and longest duration, recovery time, and time under water disagree with maximum drawdown, Recovery factor, Calmar, and Ulcer index. Those metrics must continue to describe the complete observed minute-equity curve.

## Decision

The backend streams the equity curve and includes every episode in exact aggregate statistics, but retains and transfers an episode detail only when its elapsed duration is at least 86,400 seconds. The additive analytics fields `episodeCount` and `episodeMinimumSeconds` report the exact total episode count and the response threshold. Episode numbering remains relative to all episodes, so omitted short episodes may leave gaps.

Android shows only episodes meeting the same minimum, including when parsing a legacy backend response that still sent short episodes. The screen explicitly distinguishes the number shown from the total and states that aggregate metrics still include every drawdown. Analytics requests receive a 30-second read timeout; smaller API calls retain the 8-second timeout.

## Consequences

- Long-window response size and backend episode memory scale with material episodes rather than every minute fluctuation.
- Maximum drawdown and all aggregate drawdown metrics retain their exact all-episode semantics.
- A response may report more total episodes than it contains in the `episodes` array.
- Consumers can interpret the filtered array without guessing the duration threshold.
