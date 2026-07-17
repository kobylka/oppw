CREATE DATABASE IF NOT EXISTS oppw_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE oppw_monitor;

CREATE TABLE monitor_accounts (
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

CREATE TABLE strategy_snapshots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    captured_at DATETIME(3) NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (id),
    INDEX idx_snapshot_strategy_time (strategy_key, captured_at, id),
    CONSTRAINT fk_snapshot_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key)
) ENGINE=InnoDB;

CREATE TABLE strategy_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    event_time DATETIME(3) NOT NULL,
    level VARCHAR(16) NOT NULL DEFAULT 'INFO',
    name VARCHAR(100) NOT NULL,
    result BOOLEAN NULL,
    message VARCHAR(1000) NOT NULL DEFAULT '',
    details JSON NULL,
    PRIMARY KEY (id),
    INDEX idx_event_strategy_time (strategy_key, event_time, id),
    CONSTRAINT fk_event_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key)
) ENGINE=InnoDB;

INSERT INTO monitor_accounts(account_key, display_name, account_type, broker_account_id, is_default, enabled, sort_order) VALUES
    ('REAL', 'Real account', 'REAL', '', TRUE, TRUE, 10),
    ('DEMO', 'Demo account', 'DEMO', '', FALSE, TRUE, 20)
ON DUPLICATE KEY UPDATE display_name = VALUES(display_name), account_type = VALUES(account_type), enabled = TRUE;

-- Optional retention job, run daily from cron:
-- DELETE FROM strategy_snapshots WHERE captured_at < UTC_TIMESTAMP() - INTERVAL 90 DAY;
-- DELETE FROM strategy_events WHERE event_time < UTC_TIMESTAMP() - INTERVAL 180 DAY;
