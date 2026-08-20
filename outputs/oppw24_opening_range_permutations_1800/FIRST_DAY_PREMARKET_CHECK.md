# First-position-day premarket inclusion check

The structural slow-candle confirmation was changed so that, on the position's first day only, its rolling window may include same-day premarket M1 bars. The cash opening range remains 15:30 onward; later position days remain cash-session-only.

## High-return OR5 rule

| Window | Cash-only CAGR / DD | First-day premarket CAGR / DD |
|---|---|---|
| 2018–2026 | 866.248% / 67.167% | 795.834% / 67.167% |
| 2021–2025 | 776.646% / 67.162% | 653.643% / 67.163% |
| 2022–2026 | 1,124.864% / 67.158% | 912.285% / 67.162% |
| 2025–2026 | 2,626.032% / 50.113% | 1,448.016% / 56.217% |

Premarket inclusion changes 12 full-history exits. It adds two structural exits overall. The main failures are:

- 2025-04-07: cash-only closes at +3.977%; premarket-enabled exits at -0.622%.
- 2026-06-29: cash-only closes at +1.253%; premarket-enabled exits at -1.023%.
- 2018-12-24: exit worsens from -0.599% to -0.952%.
- 2020-03-23: exit worsens from -1.525% to -1.867%.

It helps several losses, most notably 2020-11-09 (-2.947% to -0.911%), but not enough to offset the winners it cuts.

## Balanced OR5 rule

| Window | Cash-only CAGR / DD | First-day premarket CAGR / DD |
|---|---|---|
| 2018–2026 | 715.032% / 60.683% | 707.427% / 60.535% |
| 2021–2025 | 831.927% / 58.647% | 827.151% / 58.674% |
| 2022–2026 | 1,042.947% / 59.758% | 1,035.910% / 59.758% |
| 2025–2026 | 2,093.730% / 59.756% | 2,093.730% / 59.756% |

The balanced rule obtains only 0.148 percentage points of full-history drawdown improvement while losing 7.605 CAGR points. It is unchanged or slightly worse in the robustness windows.

## Conclusion

Do not include premarket bars in the first-day slow-candle confirmation. The original cash-session-only implementation is stronger and avoids using pre-entry volatility to force an early exit from a newly opened position.
