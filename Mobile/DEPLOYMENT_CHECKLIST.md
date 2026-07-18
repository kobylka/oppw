# OPPW Monitor v8 deployment checklist

- [ ] Back up MySQL.
- [ ] Confirm the v7 migration has already been imported; v8 needs no new SQL migration.
- [ ] Upload all v8 backend PHP files while preserving private `config.php`.
- [ ] Add `manual_admin_enabled` and `manual_admin_token` only when browser imports are needed.
- [ ] Verify `market-admin.php` and `trade-admin.php` return 404 while manual administration is disabled.
- [ ] Replace MT5 Python with `oppw_mt5_continuous_v35.py` and keep private config.
- [ ] Confirm current exposure equals MT5 deposit × 20.
- [ ] Confirm OH disappears after the daily scheduled open check.
- [ ] Confirm CH remains visible after market open.
- [ ] Confirm the position summary shows a potential OH/CH target.
- [ ] Confirm all-time chart shows dates, equity and deposits-to-date.
- [ ] Confirm regime text is human-readable.
- [ ] Confirm Logs switch remains fully visible on a narrow phone.
- [ ] Confirm Health displays `Heartbeat: …`.
- [ ] Test manual previous-week O/H/L/C import.
- [ ] Test manual trade import with balance before/after.
- [ ] Disable `manual_admin_enabled` after imports.
