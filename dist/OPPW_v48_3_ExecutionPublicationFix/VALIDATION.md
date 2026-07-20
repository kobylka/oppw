# OPPW MT5 v48.3 execution-publication fix

## Corrected metrics

- Entry publication is measured from `FILLED` to `PUBLISHED`.
- Exit publication remains measured from `CLOSED` to `PUBLISHED`.
- The `PUBLISHED` lifecycle stage is included in the same successful ingest request as the snapshot it describes. It is no longer delayed until a later publisher cycle.

## Deployment

1. Replace both runtime copies of `oppw_mt5_continuous.py` with v48.3.
2. Upload the matching `Mobile/backend/analytics.php`.
3. Keep `Mobile/backend/mobile-receipt.php` deployed and open the app's Overview once after restart. The app sends the actual `MOBILE_RECEIPT` event from its status refresh.

The current open demo execution receives a `PUBLISHED` stage after the updated publisher restarts. No new buy order is needed.
