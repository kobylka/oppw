# Opening-range permutation sweep: 5, 10, 20, 40, 45, 60 minutes

## Scope

- 1,800 protected-regime simulations: 300 permutations for each requested opening range.
- Protected regime: leverage override, gap-momentum, Tuesday normalization, premarket-low.
- Full history: 2018-04-13 through 2026-08-12.
- Robustness: bounded 2021-01-04 through 2025-12-31, plus 2022- and 2025-start windows through 2026-08-12.
- Initial capital 10,000, no top-ups, tax enabled.
- Other dimensions held constant: entry loss 0.5–2.5%; persistence 1/3/5/10/15m; slow candle 30/45/60m; slow decline 0.75–1.50%.

1,618 of 1,800 rules improved full-history daily drawdown. Six rules were globally Pareto-efficient, and all six used a 5-minute opening range.

## Recommended high-return rule

Exit at the completed M1 close when all conditions hold:

1. current minute low is at least 0.50% below trade entry;
2. the first 5 cash-session minutes have completed;
3. current minute closes below the 5-minute opening-range low;
4. rolling 60-minute candle falls at least 1.50% from open to low.

Persistence is one completed close.

| Window | Baseline CAGR / DD | OR5 high-return CAGR / DD | Exits |
|---|---|---|---:|
| 2018–2026 | 851.217% / 84.672% | 866.250% / 67.167% | 38 |
| 2021–2025 | 742.437% / 79.016% | 776.650% / 67.162% | 25 |
| 2022–2026 | 983.911% / 78.945% | 1,124.864% / 67.158% | 22 |
| 2025–2026 | 1,512.141% / 65.819% | 2,626.032% / 50.113% | 4 |

This rule improves both CAGR and drawdown in every tested window. It also slightly dominates the prior OR15 winner on full history, 2021–2025, and the 2022-start window; their 2025-start results are identical.

## Recommended balanced rule

Exit when all conditions hold:

1. current minute low is at least 1.00% below entry;
2. first 5 cash-session minutes have completed;
3. price closes below the 5-minute opening-range low for 15 consecutive minutes;
4. rolling 30-minute candle falls at least 1.25% from open to low.

| Window | Baseline CAGR / DD | OR5 balanced CAGR / DD | Exits |
|---|---|---|---:|
| 2018–2026 | 851.217% / 84.672% | 715.030% / 60.683% | 32 |
| 2021–2025 | 742.437% / 79.016% | 831.930% / 58.647% | 19 |
| 2022–2026 | 983.911% / 78.945% | 1,042.947% / 59.758% | 18 |
| 2025–2026 | 1,512.141% / 65.819% | 2,093.730% / 59.756% | 4 |

The balanced rule retains 84.0% of full-history CAGR while improving drawdown by 23.989 percentage points. It improves both metrics in all three robustness windows.

## Range comparison

Best drawdown result among rules retaining at least 80% of baseline full-history CAGR:

| Opening range | CAGR | Daily DD | DD improvement |
|---:|---:|---:|---:|
| 5m | 715.030% | 60.683% | 23.989 pp |
| 10m | 692.590% | 66.493% | 18.179 pp |
| 20m | 690.340% | 67.167% | 17.506 pp |
| 40m | 691.990% | 70.537% | 14.136 pp |
| 45m | 699.610% | 70.537% | 14.136 pp |
| 60m | 689.370% | 69.705% | 14.967 pp |

The 5-minute range is the clear winner within this parameter grid. These remain in-sample searches; the overlapping robustness windows demonstrate stability but are not held-out evidence.
