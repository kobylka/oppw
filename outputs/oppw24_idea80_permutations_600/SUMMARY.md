# Idea 80 permutation sweep

## Scope

- 600 protected-regime permutations: 300 using a 15-minute opening range and 300 using 30 minutes.
- Inclusive full-history period: 2018-04-13 through 2026-08-12.
- Extra bounded robustness period: 2021-01-04 through 2025-12-31.
- Additional checks: 2022-01-03 and 2025-01-06 starts through 2026-08-12.
- Initial capital 10,000, no top-ups, tax enabled.
- Grid dimensions: opening range 15/30m; entry loss 0.5/1.0/1.5/2.0/2.5%; persistence 1/3/5/10/15m; slow candle 30/45/60m; slow decline 0.75/1.0/1.25/1.5%.

## Outcome

507 of 600 rules improved full-history daily drawdown. Seven were Pareto-efficient. The high-CAGR frontier strongly favored the 15-minute opening range.

## Recommended permutation 12

Exit at the completed M1 close when all conditions hold:

1. the position is at least 0.50% below entry, measured using the current minute low;
2. the first 15 cash-session minutes have completed;
3. the current minute closes below that 15-minute opening-range low;
4. the rolling 60-minute candle has declined at least 1.50% from its open to its low.

Persistence is one completed close. Existing catastrophic stops retain priority.

## Comparison

| Window | Rule | CAGR | Daily DD | Structural exits |
|---|---|---:|---:|---:|
| Full history | Baseline | 851.217% | 84.672% | 0 |
| Full history | Original idea 80, OR30 | 659.456% | 68.406% | 32 |
| Full history | Permutation 12, OR15 | 832.219% | 67.167% | 38 |
| 2021-2025 | Baseline | 742.437% | 79.016% | 0 |
| 2021-2025 | Original idea 80, OR30 | 608.769% | 68.402% | 20 |
| 2021-2025 | Permutation 12, OR15 | 751.908% | 67.165% | 25 |
| 2022 start | Baseline | 983.911% | 78.945% | 0 |
| 2022 start | Original idea 80, OR30 | 866.694% | 68.408% | 17 |
| 2022 start | Permutation 12, OR15 | 1,087.582% | 67.161% | 22 |
| 2025 start | Baseline | 1,512.141% | 65.819% | 0 |
| 2025 start | Original idea 80, OR30 | 1,962.399% | 49.906% | 4 |
| 2025 start | Permutation 12, OR15 | 2,626.032% | 50.113% | 4 |

Permutation 12 dominates original idea 80 on full history, 2021-2025, and the 2022-start window. In the 2025-start window idea 80 has 0.208 percentage points lower daily drawdown, but permutation 12 has 663.633 percentage points higher CAGR and substantially lower closed-trade drawdown.

## More aggressive alternative

Permutation 122 uses OR15, entry loss 1.50%, one-minute persistence, and a rolling 30-minute decline of 1.00%. It reaches 65.249% full-history daily drawdown and 60.519% in 2021-2025, but full-history CAGR falls to 654.804%. Permutation 12 offers the stronger return/drawdown balance.

These are in-sample parameter searches. The bounded window overlaps the optimization history and is a stability check, not a truly held-out validation set.
