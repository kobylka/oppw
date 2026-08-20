# Logical OR combination: OpeningRange5 or OpeningRange15

Both complete rules use entry loss 0.50%, one-close persistence, and a rolling cash-session-only 60-minute open-to-low decline of 1.50%. The combined rule exits when either complete rule becomes true.

| Window | Baseline CAGR / DD | OR5 CAGR / DD | OR15 CAGR / DD | Combined CAGR / DD |
|---|---|---|---|---|
| 2018–2026 | 851.217% / 84.672% | 866.248% / 67.167% | 832.219% / 67.167% | 866.248% / 67.167% |
| 2021–2025 | 742.437% / 79.016% | 776.646% / 67.162% | 751.908% / 67.165% | 776.646% / 67.162% |
| 2021–2026 | 751.490% / 79.016% | 872.228% / 67.162% | 847.751% / 67.165% | 872.228% / 67.162% |
| 2022–2026 | 983.911% / 78.945% | 1,124.864% / 67.158% | 1,087.582% / 67.161% | 1,124.864% / 67.158% |
| 2025–2026 | 1,512.141% / 65.819% | 2,626.032% / 50.113% | 2,626.032% / 50.113% | 2,626.032% / 50.113% |

The two rules trigger on identical trade-entry dates: 38 full-history exits, 25 during 2021–2025, 26 during 2021–2026, 22 during 2022–2026, and 4 during 2025–2026. On every trade where timestamps differ, OpeningRange5 triggers first. Consequently, a logical OR combination is behaviorally identical to OpeningRange5 alone. OpeningRange15 is redundant in the combined rule.
