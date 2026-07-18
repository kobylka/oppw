# v11 deployment checklist

1. Confirm MT5 loop v41 or newer is running for the selected account.
2. Confirm the latest stored snapshot contains `potentialPosition` while the account is flat.
3. Preserve the existing Android `local.properties`.
4. Replace the complete Android project with v11.
5. Build with JDK 17 and Android SDK 37.
6. Install using the same signing key so the paired session remains readable.
7. Open Position while flat and verify:
   - potential volume;
   - current price;
   - required deposit;
   - chosen 8x/10x leverage;
   - leverage explanation;
   - effective leverage equal to required deposit divided by balance.
8. Open Position while a trade is active and verify the existing open-position layout is unchanged.

No database migration is required. The existing v9.1.1 `status.php` preserves fields from the stored snapshot, so it forwards `potentialPosition` without a schema change.
