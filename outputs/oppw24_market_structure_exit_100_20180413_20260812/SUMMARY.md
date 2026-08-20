# Protected OPPW24: 100 additional market-structure ideas

## Scope

- Protected regime with leverage override, gap-momentum, Tuesday normalization, and premarket-low.
- Inclusive range: 2018-04-13 through 2026-08-12.
- Initial balance 10,000; no top-ups; tax enabled.
- Four new families: previous-session-range stops, intraday range-expansion reversals, lower-close sequences, and persistent breaks below the previous session low.
- Every reference uses only completed prior-session or current-minute data.

## Baseline

| CAGR | Daily marked-equity DD | Closed-trade DD |
|---:|---:|---:|
| 851.217% | 84.672% | 82.076% |

Eighty-four of 100 ideas improved full-history daily drawdown.

## Full-history ideas that improved both metrics

| Idea | Rule | Exits | CAGR | Daily DD | DD improvement |
|---:|---|---:|---:|---:|---:|
| 53 | Two consecutive lower M1 closes with combined decline >=0.75% | 4 | 898.158% | 79.072% | 5.600 pp |
| 59 | Three consecutive lower M1 closes with combined decline >=1.00% | 3 | 859.111% | 80.190% | 4.483 pp |
| 13 | Stop at entry minus 3.5 times previous session range | 7 | 873.250% | 81.759% | 2.914 pp |

## Subperiod robustness

| Start | Rule | CAGR | Daily DD | Exits |
|---|---|---:|---:|---:|
| 2022-01-03 | Baseline | 983.911% | 78.945% | 0 |
| 2022-01-03 | Idea 53 | 884.499% | 78.945% | 2 |
| 2022-01-03 | Idea 59 | 1,006.434% | 78.945% | 1 |
| 2022-01-03 | Idea 13 | 974.933% | 78.945% | 3 |
| 2025-01-06 | Baseline | 1,512.141% | 65.819% | 0 |
| 2025-01-06 | Idea 53 | 1,295.960% | 65.819% | 1 |
| 2025-01-06 | Idea 59 | 1,609.975% | 65.819% | 1 |
| 2025-01-06 | Idea 13 | 1,512.141% | 65.819% | 0 |

## Conclusion

No rule provides robust drawdown protection across the subperiods. Idea 53 looks excellent over full history but its drawdown improvement is attributable to older trades; after 2022 it reduces CAGR without changing maximum drawdown. Idea 59 increases CAGR in each measured window, but its recent drawdown is unchanged, so it is a possible return-enhancement hypothesis rather than a risk-control solution.

The preceding structural idea 80 remains the best tested drawdown rule because it reduces drawdown in the full, 2022-start, and 2025-start windows.
