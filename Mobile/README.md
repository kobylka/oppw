# OPPW Android v12.3 + MT5 v44

This package is based on the public `kobylka/oppw` v12.2/v43 source.

## Implemented fixes

### Effective leverage

Potential-position effective leverage is now:

```text
20 × MT5 required deposit / account balance
```

The deposit remains the live result of `mt5.order_calc_margin(proposed volume, current BUY price)`. The broker account's configured leverage is retained as metadata but is no longer used to multiply the deposit. Android also recomputes the same formula as a compatibility fallback.

### Maximum 50% account loss at hard stop

The strategy first calculates its requested hard stop. It then asks MT5 for the projected P/L at that price. If the projected account return is below `-50%`, the stop is moved closer using an MT5 `order_calc_profit` binary search and rounded toward the safer price.

The capped stop is used by:

- the pre-trade preview;
- the actual BUY request;
- ongoing broker-side hard-SL protection;
- the HARD SL what-if scenario.

### Mobile formatting

- Margin usage and margin level no longer show a leading `+` sign.
- The potential hard-stop panel no longer shows the underlying-stop formula or an `Underlying stop` field.
- It shows the final stop price, cash P/L, account return, and whether the 50% cap was applied.

### Previous trade in decision recorder

The publisher now prefers the last publisher-labeled strategy result stored in account-scoped state. This prevents an erroneous zero-valued MT5 history reconstruction from replacing a known `-0.5%` previous trade. The Android screen also falls back to `lastClosedTrade` when an older decision payload reports zero.

## Deployment

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& ".\apply-v12.3-v44.ps1" -ProjectRoot "D:\oppw"

cd D:\oppw\Mobile
.\gradlew.bat clean assembleDebug
```

Stop both executor and publisher before replacing the MT5 script. Restart both from the same v44 source. No backend or SQL migration is required.
