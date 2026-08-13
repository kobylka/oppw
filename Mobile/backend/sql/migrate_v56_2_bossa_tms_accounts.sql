-- Preserve the historical DEMO/REAL keys while giving the existing Bossa
-- accounts their operator-facing names. Prepare TMS identities disabled so
-- they cannot enter supervisor assignments before both nodes have credentials.
START TRANSACTION;

UPDATE monitor_accounts
   SET display_name = 'DEMO BOSSA'
 WHERE account_key = 'DEMO';

UPDATE monitor_accounts
   SET display_name = 'REAL BOSSA'
 WHERE account_key = 'REAL';

INSERT INTO monitor_accounts(
    account_key, display_name, account_type, broker_account_id,
    is_default, enabled, sort_order
) VALUES
    ('REAL_TMS', 'REAL TMS', 'REAL', '', FALSE, FALSE, 30),
    ('DEMO_TMS', 'DEMO TMS', 'DEMO', '', FALSE, FALSE, 40)
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name),
    account_type = VALUES(account_type);

COMMIT;
