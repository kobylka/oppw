# OR5 confirmation-window sweep: 15 and 75 minutes

Protected-regime command basis:

`oppw24.py --leverage_override --gap-momentum --tuesday-normalization --premarket-low`

Backtests use a 10,000 initial balance, no top-ups, and tax enabled. The full
window is 2018-04-13 through 2026-08-12 inclusive.

## Sweep

The 200 permutations combine:

- OR5 opening range
- confirmation window: 15 or 75 minutes
- entry loss: 0.50%, 1.00%, 1.50%, 2.00%, or 2.50%
- persistence: 1, 3, 5, 10, or 15 minutes
- rolling open-to-low decline: 0.75%, 1.00%, 1.25%, or 1.50%

180 of 200 permutations improved full-history daily mark-to-market drawdown.

## Selected rules

15-minute winner (permutation 19): entry loss at least 0.50%, five consecutive
minute closes below OR5, and rolling 15-minute open-to-low decline at least
1.25%.

75-minute winner (permutation 32): entry loss at least 0.50%, ten consecutive
minute closes below OR5, and rolling 75-minute open-to-low decline at least
1.50%.

The alternative 75-minute higher-full-CAGR rule (permutation 40) uses the same
thresholds with 15-minute persistence.

## Results

| Window | Rule | CAGR | Daily DD | Exits |
|---|---:|---:|---:|---:|
| 2018-04-13–2026-08-12 | Baseline | 851.22% | 84.67% | 0 |
| 2018-04-13–2026-08-12 | 15m winner | 855.78% | 65.76% | 16 |
| 2018-04-13–2026-08-12 | 75m winner | 814.03% | 59.56% | 47 |
| 2018-04-13–2026-08-12 | 75m higher-CAGR variant | 821.82% | 61.47% | 47 |
| 2021-01-04–2025-12-31 | Baseline | 742.44% | 79.02% | 0 |
| 2021-01-04–2025-12-31 | 15m winner | 740.96% | 65.76% | 10 |
| 2021-01-04–2025-12-31 | 75m winner | 837.37% | 57.39% | 28 |
| 2022-01-03–2026-08-12 | Baseline | 983.91% | 78.94% | 0 |
| 2022-01-03–2026-08-12 | 15m winner | 1013.07% | 65.76% | 10 |
| 2022-01-03–2026-08-12 | 75m winner | 1228.88% | 57.22% | 24 |
| 2025-01-06–2026-08-12 | Baseline | 1512.14% | 65.82% | 0 |
| 2025-01-06–2026-08-12 | 15m winner | 1424.72% | 54.14% | 2 |
| 2025-01-06–2026-08-12 | 75m winner | 2525.65% | 50.08% | 4 |

The 15-minute candle first becomes complete at 15:44 market time. The
75-minute candle first becomes complete at 16:44. OR5 itself is complete after
15:34; persistence and the confirmation-window availability can delay an exit.
