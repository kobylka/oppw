USE oppw_monitor;

CREATE TABLE IF NOT EXISTS monitor_accounts (
    account_key VARCHAR(64) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    account_type VARCHAR(16) NOT NULL DEFAULT 'OTHER',
    broker_account_id VARCHAR(64) NOT NULL DEFAULT '',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INT NOT NULL DEFAULT 100,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (account_key),
    INDEX idx_monitor_accounts_enabled_sort (enabled, sort_order, display_name)
) ENGINE=InnoDB;

INSERT INTO monitor_accounts(account_key, display_name, account_type, broker_account_id, is_default, enabled, sort_order) VALUES
    ('REAL', 'Real account', 'REAL', '', TRUE, TRUE, 10),
    ('DEMO', 'Demo account', 'DEMO', '', FALSE, TRUE, 20)
ON DUPLICATE KEY UPDATE display_name = VALUES(display_name), account_type = VALUES(account_type), enabled = TRUE;

-- Register any existing strategy keys before adding foreign keys, for example:
-- INSERT IGNORE INTO monitor_accounts(account_key, display_name, account_type) SELECT DISTINCT strategy_key, strategy_key, 'OTHER' FROM strategy_snapshots;
-- INSERT IGNORE INTO monitor_accounts(account_key, display_name, account_type) SELECT DISTINCT strategy_key, strategy_key, 'OTHER' FROM strategy_events;
