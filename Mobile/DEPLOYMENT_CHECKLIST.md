# OPPW Monitor v6 deployment checklist

- [ ] Back up the MySQL database.
- [ ] Import `backend/sql/migrate_v6.sql` through phpMyAdmin.
- [ ] Confirm the four new tables exist.
- [ ] Upload the complete v6 backend, retaining the private `config.php`.
- [ ] Confirm `health.php` returns `{"ok":true,...}`.
- [ ] Replace the strategy file with `mt5/oppw_mt5_continuous_v33.py`.
- [ ] Keep the existing private MT5 config and credentials outside Git.
- [ ] Confirm the strategy logs `MONITOR_MINUTE_STATUS_QUEUED` every minute.
- [ ] Set an unquoted HTTPS URL in `local.properties`.
- [ ] Build and install the v6 APK.
- [ ] Swipe through all four pages.
- [ ] Confirm freshness values increase every second.
- [ ] Confirm Settings is the only location containing Unpair.
- [ ] Confirm market statistics populate after minute snapshots arrive.
- [ ] Confirm daily/weekly/all-time charts load.
- [ ] Confirm Logs filters work independently.
