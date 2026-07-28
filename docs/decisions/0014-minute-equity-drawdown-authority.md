# ADR 0014: Minute-equity drawdown authority

- Status: Superseded by ADR 0016
- Date: 2026-07-28

## Context

Mobile drawdown charts, episodes, depths, and durations were reconstructed from closed-trade returns. That curve omitted unrealized intratrade troughs even though `strategy_equity_points` already stores account equity by minute. Other analytics fields mixed closed-trade, daily-close, and drawdown semantics: maximum currency drawdown used daily closes, while Calmar and Ulcer also used a daily curve. A position could therefore suffer a material intraday drawdown that no displayed drawdown metric reported.

Sending every retained minute to Android is not a safe replacement. A long window can contain hundreds of thousands of points, and computing episode metrics from a downsampled chart would make results depend on presentation sampling. External top-ups and withdrawals must also not appear as investment gains or losses.

## Decision

`analytics.php` derives every portfolio-drawdown measure from the time-ordered `strategy_equity_points` curve for the selected accounts and rolling window. It combines same-minute account samples, carries each account's last value between its updates, and constructs a cash-flow-adjusted equity index using authoritative `account_cash_flows`. Maximum percentage and currency drawdown, episode depth and timing, time under water, Recovery factor, Calmar denominator, and Ulcer index all use that curve.

The backend computes exact aggregate statistics and episodes before bounding the chart series. The response identifies the source granularity, total and minute sample counts, cash-flow adjustment, exact-statistics status, and whether the chart series was downsampled. Each retained minute point and episode carries any active position trade keys available from `position_ticket`.

Minute history remains hot for the retention period. When a requested window reaches older history whose minute rows were archived, `strategy_equity_daily` supplies explicit `DAILY_FALLBACK` points only for account-days without minute rows. Minute rows always win when both forms exist. The Android app consumes the backend's exact aggregates and episodes; it calculates from the returned series only as compatibility behavior for an older backend.

Account/scope and rolling-window filters define the portfolio drawdown curve. Leverage, exit-reason, and class filters remain trade-projection filters because account equity cannot be truthfully decomposed into a hypothetical filtered portfolio from the stored observations. The UI states this boundary.

## Consequences

- Intratrade unrealized losses are visible in every drawdown-related metric.
- Cash movements do not create artificial drawdowns or recoveries.
- Android rendering stays bounded without sacrificing metric or episode accuracy.
- Drawdown precision is minute-level inside hot retention and explicitly daily-level for older retained history.
- The analytics payload changes additively; legacy point fields remain present for already-deployed Android clients.
