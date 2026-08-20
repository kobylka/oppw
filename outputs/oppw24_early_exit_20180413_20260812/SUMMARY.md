# OPPW24 rolling-candle early-exit sweep

## Scope

- Inclusive history: 2018-04-13 through 2026-08-12.
- Initial balance: 10,000.
- Top-ups/deposits: disabled and verified; every run retained deposited capital of 10,000.
- Tax: enabled through the existing `oppw24.py` annual tax behavior.
- Sizing: `--leverage_override` enabled.
- Configurations:
  1. leverage override only;
  2. leverage override plus gap-momentum, Tuesday normalization, and premarket-low protection.
- Exactly 200 ideas per configuration: 120 single-timescale rules and 80 two-timescale confirmation rules.
- A signal is evaluated after the rolling candle closes and exits at that M1 close. Windows do not cross a daily-session boundary or precede the position entry. Existing catastrophic stops have priority.

## Baselines

| Configuration | Trades | Final balance | CAGR | Closed-trade DD | Daily marked-equity DD |
|---|---:|---:|---:|---:|---:|
| Leverage override | 433 | 4,569,966,138.57 | 380.374% | 96.948% | 97.336% |
| Protected | 376 | 1,329,659,518,073.24 | 851.217% | 82.076% | 84.672% |

## Recommended configuration-specific rules

| Configuration | Rule | Early exits | CAGR | CAGR change | Daily DD | DD improvement |
|---|---|---:|---:|---:|---:|---:|
| Leverage override | 60m <= -1.480% | 88 | 380.207% | -0.168 pp | 92.296% | +5.039 pp |
| Protected, no-CAGR-sacrifice choice | 3m <= -1.000% | 11 | 866.451% | +15.235 pp | 83.137% | +1.536 pp |
| Protected, balanced DD choice | 5m <= -0.565% AND 30m <= -1.085% | 37 | 757.124% | -94.093 pp | 65.870% | +18.803 pp |

The plain leverage-override recommendation is idea 105. The protected no-sacrifice choice is idea 35. The protected balanced drawdown choice is idea 164.

## One common rule for both configurations

Idea 105, `60m <= -1.480%`, improves drawdown in both configurations:

| Configuration | CAGR | CAGR retention | Daily DD | DD improvement |
|---|---:|---:|---:|---:|
| Leverage override | 380.207% | 99.956% | 92.296% | +5.039 pp |
| Protected | 704.673% | 82.784% | 68.135% | +16.538 pp |

Idea 164 retains more protected CAGR and produces lower protected drawdown, but improves plain leverage-override drawdown by only 1.492 points. Idea 105 is therefore the stronger shared rule when minimum improvement across both configurations matters.

## Aggressive drawdown floor

Idea 41, `5m <= -0.400%`, produced the lowest daily drawdown in both configurations, but the CAGR cost was severe:

| Configuration | CAGR | Daily DD | DD improvement |
|---|---:|---:|---:|
| Leverage override | 60.892% | 67.905% | +29.431 pp |
| Protected | 86.169% | 59.191% | +25.481 pp |

This is not recommended when only a moderate CAGR reduction is acceptable.

## Artifacts

- `results.csv`: all 400 idea/configuration results.
- `results.json`: baselines, exact rule clauses, and all detailed results.
