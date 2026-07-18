# v10.1 changelog

## Restored from v9.1 without modification

- `auth/AuthModels.kt`
- `auth/SecureSessionStore.kt`
- `data/StatusApiClient.kt`
- `data/StatusRepository.kt`
- Nested v9.1 `JsonParser.parseAuthSession()` contract
- Account selection, access-token refresh, refresh-token rotation, encrypted persistence, unpairing and push-token registration

## v10 functionality retained

- Weekend scheduling override also applies to a carried open position.
- Equity curves use timestamp-based x coordinates.
- Closest condition is not repeated.
- Sharpe and Sortino use closed trades only.
- Routine logs are hidden before first display and the switch recreates the paging query.

## Other correction

- `Common.kt` is the original v9.1 implementation and does not import or inspect internal Compose `RowColumnParentData.weight` state.

Version code: 13

Version name: 10.1.0
