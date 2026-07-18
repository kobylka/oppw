# v10 functional test plan

## Weekend carried position

1. Use a status payload containing an open position and a stale Friday `nextAction=OH` value.
2. Set the device time to Saturday or Sunday in Europe/Warsaw.
3. Verify Overview shows phase Weekend, Market CLOSED, next action None, and no countdown.
4. Verify Position still shows the open trade and the weekend warning.

## Time-scaled equity chart

1. Supply one point on Monday and many points on Tuesday.
2. Confirm the Monday-to-Tuesday distance is determined by elapsed time.
3. Confirm adding more points within Tuesday does not move Monday or change the day-width ratio.

## Condition de-duplication

1. Return a closest condition and an identical item in conditions.
2. Verify the dedicated Closest condition card appears once.
3. Verify the identical condition does not appear under All other conditions.
4. Verify a condition with the same name but a different target price remains visible.

## Closed-trade ratios

1. Return two or more closed trades with `profit` and `balanceBefore`.
2. Include an open trade with an extreme unrealized result.
3. Verify the sample count excludes the open trade.
4. Verify Sharpe/Sortino do not change when only the open trade changes.
5. Verify insufficient/zero-denominator cases show N/A rather than NaN.

## Routine logs

1. Open Logs after a fresh app start without touching the switch.
2. Verify OH, CH, TO, SL, TSL*, POSITION_IS_OPEN, scheduling checks, and condition-report rows are absent.
3. Enable Show routine condition checks.
4. Verify the pager reloads and those rows appear.
5. Change accounts and verify the switch starts off for the newly selected account.
