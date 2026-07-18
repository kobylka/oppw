# OPPW Monitor Android v11 changelog

## Added

- `PotentialPosition` data model.
- Parsing of `snapshot.potentialPosition` and `snapshot.potential_position`.
- CamelCase and snake_case parsing for all potential-trade fields.
- Flat Position-screen preview showing volume, current price, required deposit, account balance, strategy leverage, leverage reason, effective leverage, potential notional and sizing units.
- Explicit unavailable state when MT5 cannot calculate the preview.
- Explicit compatibility message when the backend has no v41 potential-position data.
- Unit tests for `required deposit / balance` effective-leverage calculation.

## Preserved

- v9.1 authentication source files unchanged.
- v10.1.1 log paging and filtering.
- v10 weekend, chart, conditions and closed-trade analytics fixes.
- Open-position display and risk information.

## Version

- `versionCode`: 15
- `versionName`: 11.0.0
