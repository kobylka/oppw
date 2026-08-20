# Protected OPPW24: 100 structural early-exit ideas

## Scope

- Protected configuration: leverage override, gap-momentum, Tuesday normalization, and premarket-low.
- Inclusive range: 2018-04-13 through 2026-08-12.
- Initial capital: 10,000; no top-ups; tax enabled.
- One hundred distinct rules across four families: entry-loss plus persistence, failed recovery, session-loss plus persistence, and entry-loss plus slower-candle confirmation.
- All rules require a break below an observable cash-session opening-range low. Signals execute at the completed M1 close without look-ahead.

## Full-history baseline

| CAGR | Daily marked-equity DD | Closed-trade DD |
|---:|---:|---:|
| 851.217% | 84.672% | 82.076% |

Eighty-five of 100 ideas improved daily drawdown. No idea both improved drawdown and retained at least 80% of full-history baseline CAGR.

## Pareto-efficient ideas

| Idea | Rule | Early exits | CAGR | Daily DD | DD improvement |
|---:|---|---:|---:|---:|---:|
| 80 | Entry loss >=1.0%; below 30m opening-range low for 3m; rolling 60m decline >=1.5% | 32 | 659.456% | 68.406% | 16.266 pp |
| 83 | Entry loss >=1.5%; below 30m opening-range low for 3m; rolling 30m decline >=1.0% | 36 | 591.562% | 68.232% | 16.440 pp |

## Robustness by start date

| Start | Rule | CAGR | Daily DD | Early exits |
|---|---|---:|---:|---:|
| 2018-04-13 | Baseline | 851.217% | 84.672% | 0 |
| 2018-04-13 | Idea 80 | 659.456% | 68.406% | 32 |
| 2018-04-13 | Idea 83 | 591.562% | 68.232% | 36 |
| 2022-01-03 | Baseline | 983.911% | 78.945% | 0 |
| 2022-01-03 | Idea 80 | 866.694% | 68.408% | 17 |
| 2022-01-03 | Idea 83 | 915.199% | 65.249% | 18 |
| 2025-01-06 | Baseline | 1,512.141% | 65.819% | 0 |
| 2025-01-06 | Idea 80 | 1,962.399% | 49.906% | 4 |
| 2025-01-06 | Idea 83 | 1,374.370% | 65.246% | 6 |

## Conclusion

Idea 80 is the preferred candidate. Idea 83 obtains only 0.174 percentage points more full-history drawdown relief, but sacrifices another 67.894 percentage points of CAGR and is much weaker over the 2025-start window. Idea 80 improves drawdown in all three windows and improves both metrics in the most recent window.

This is still an in-sample research result. It should be evaluated using a genuinely held-out period or walk-forward folds before production use.
