# Deployment checklist — multi-account

## Server

- [ ] MySQL backup created.
- [ ] `monitor_accounts` table created.
- [ ] `REAL` and `DEMO` rows exist.
- [ ] Any additional accounts inserted with unique `account_key` values.
- [ ] `accounts.php`, `status.php`, and `ingest.php` deployed.
- [ ] HTTPS certificate valid.
- [ ] Read and write tokens are different.
- [ ] `accounts.php` returns all enabled accounts.
- [ ] `status.php?account=REAL` and `status.php?account=DEMO` return separate data.

## Publishers

- [ ] Real process uses `OPPW_MONITOR_ACCOUNT_KEY=REAL`.
- [ ] Demo process uses `OPPW_MONITOR_ACCOUNT_KEY=DEMO`.
- [ ] Each snapshot contains the matching `connection.accountId`.
- [ ] Publisher failures cannot block the trading loop.

## Android

- [ ] `local.properties` contains HTTPS API URL and read token.
- [ ] Gradle sync completes with JDK 17.
- [ ] Debug APK installs on Samsung Galaxy A53.
- [ ] Account wallet icon lists Real and Demo.
- [ ] Switching account changes position, equity, and logs.
- [ ] Selected account survives app restart.
- [ ] No trading controls are present.
