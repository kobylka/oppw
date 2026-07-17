# Deployment checklist

## Backend

- [ ] Import `backend/sql/schema.sql` or `migrate_auth.sql`.
- [ ] Create `backend/config.php` from the example.
- [ ] Generate independent database, writer and HMAC secrets.
- [ ] Deploy only behind HTTPS with a valid certificate.
- [ ] Confirm `config.php`, `lib.php`, `admin/`, `sql/` and `publisher/` are inaccessible over HTTP.
- [ ] Test `health.php`.
- [ ] Configure the MT5 publisher with the write token.
- [ ] Schedule `admin/cleanup.php` daily.

## Android

- [ ] Set only `OPPW_API_BASE_URL` in `local.properties`.
- [ ] Run Gradle sync with JDK 17.
- [ ] Build and install the APK.
- [ ] Generate a one-time pairing code.
- [ ] Pair the phone and verify only assigned accounts appear.
- [ ] Wait at least 15 minutes and verify transparent access-token refresh.
- [ ] Revoke the device on the server and verify the app returns to pairing after the current access token is rejected.
- [ ] Generate and protect the release signing key outside Git.
