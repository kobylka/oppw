# OPPW MT5 v49

Build:

```text
2026-07-21-immutable-hard-stop-market-be-v49
```

## Immutable filled-position hard stop

The BUY request still carries a provisional broker-side SL calculated from the
requested ask. Once MT5 exposes the filled position, v49 calculates one
definitive hard SL from:

- actual `position.price_open`;
- actual filled `position.volume`;
- MT5 account balance at fill reconciliation;
- selected strategy leverage;
- `order_calc_profit()` account-currency conversion at that moment;
- symbol tick size and the selected account-loss-cap policy.

The state file persists:

```text
immutable_hard_sl_position_identifier
immutable_hard_sl_price
immutable_hard_sl_entry_price
immutable_hard_sl_volume
immutable_hard_sl_balance
immutable_hard_sl_leverage
immutable_hard_sl_profit
immutable_hard_sl_account_currency
immutable_hard_sl_value_per_price_unit
immutable_hard_sl_tick_size
immutable_hard_sl_account_loss_cap_applied
immutable_hard_sl_locked_at
immutable_hard_sl_source
```

The first post-fill pass may correct the provisional SL in either direction.
After confirmation, normal protection follows:

```text
desired SL = max(immutable hard SL, deliberate tighter TSL, confirmed tighter broker SL)
```

Deposits, withdrawals, later balance changes and later account-currency
conversion quotes do not recalculate the live position's hard-stop baseline.
The standard loop no longer calls `capped_hard_stop()` for an already-locked
position.

The baseline can subsequently change only through:

- the single post-fill correction;
- Thursday TSL tightening;
- explicit exit protection after a failed market close or crossed SL;
- restoration when broker protection is missing;
- the position closing and a different filled position receiving a new lock.

For a legacy open position that has no v49 fields, startup creates one
`RECOVERY_INITIALIZATION` lock and then treats it as immutable.

## Break-even exits

These conditions now submit the existing globally fenced market-SELL request:

```text
BEPRE
BEO
BH
```

Their primary path is no longer `arm_exit()` or a near-market SL/TP bracket.
If a market SELL is accepted but the position remains visible, the existing
latched-exit fallback may still install a protective bracket on a later cycle.

The former crossed-TP protection-latch reason does not exist anywhere in the
v49 source. If an armed break-even TP is already behind the live market, the
position is sent through the market-BH close path.

`PROTECTION_SL_ALREADY_CROSSED` remains as the emergency protective-bracket
path when the market has already crossed the required SL.

## Installation

1. Stop both EXECUTOR and PUBLISHER.
2. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass `
     -File .\install_v49.ps1 `
     -RepoRoot D:\oppw
   ```

3. Restart PUBLISHER first.
4. Restart EXECUTOR second.
5. Confirm the executor log contains:

   ```text
   build=2026-07-21-immutable-hard-stop-market-be-v49
   ```

6. For an open position, confirm exactly one lock event:

   ```text
   EVENT IMMUTABLE_HARD_SL_LOCKED ...
   ```

Private Demo and Real configuration files are not overwritten. No backend,
database migration or Android update is required.

## Conservative profile

The existing optional flag remains:

```powershell
python .\oppw_mt5_continuous.py --account demo --mode executor --conservative-multiplier
```

When this profile activates the 50% account-loss cap, the definitive capped
price is calculated only at fill reconciliation and then frozen.
