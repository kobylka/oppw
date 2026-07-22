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
    event_hash CHAR(64) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_strategy_event_hash (strategy_key, event_hash),
    INDEX idx_event_strategy_time (strategy_key, event_time, id),
    INDEX idx_event_strategy_id (strategy_key, id),
    INDEX idx_event_strategy_name (strategy_key, name, id),
    CONSTRAINT fk_event_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key)
) ENGINE=InnoDB;

CREATE TABLE monitor_devices (
    device_id CHAR(32) NOT NULL,
    device_name VARCHAR(100) NOT NULL,
    refresh_token_hash CHAR(64) NOT NULL,
    refresh_expires_at DATETIME(3) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    last_seen_at DATETIME(3) NULL,
    PRIMARY KEY (device_id),
    INDEX idx_devices_enabled_expiry (enabled, refresh_expires_at)
) ENGINE=InnoDB;

CREATE TABLE monitor_device_accounts (
    device_id CHAR(32) NOT NULL,
    account_key VARCHAR(64) NOT NULL,
    can_control_service BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (device_id, account_key),
    CONSTRAINT fk_device_accounts_device FOREIGN KEY (device_id) REFERENCES monitor_devices(device_id) ON DELETE CASCADE,
    CONSTRAINT fk_device_accounts_account FOREIGN KEY (account_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE monitor_access_tokens (
    token_hash CHAR(64) NOT NULL,
    device_id CHAR(32) NOT NULL,
    expires_at DATETIME(3) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    last_used_at DATETIME(3) NULL,
    revoked_at DATETIME(3) NULL,
    PRIMARY KEY (token_hash),
    INDEX idx_access_device_expiry (device_id, expires_at, revoked_at),
    CONSTRAINT fk_access_device FOREIGN KEY (device_id) REFERENCES monitor_devices(device_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE monitor_pairing_codes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code_hash CHAR(64) NOT NULL,
    label VARCHAR(100) NOT NULL DEFAULT '',
    expires_at DATETIME(3) NOT NULL,
    consumed_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_pairing_code_hash (code_hash),
    INDEX idx_pairing_expiry (expires_at, consumed_at)
) ENGINE=InnoDB;

CREATE TABLE monitor_pairing_code_accounts (
    pairing_code_id BIGINT UNSIGNED NOT NULL,
    account_key VARCHAR(64) NOT NULL,
    can_control_service BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (pairing_code_id, account_key),
    CONSTRAINT fk_pair_code_accounts_code FOREIGN KEY (pairing_code_id) REFERENCES monitor_pairing_codes(id) ON DELETE CASCADE,
    CONSTRAINT fk_pair_code_accounts_account FOREIGN KEY (account_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE auth_rate_limits (
    rate_key CHAR(64) NOT NULL,
    window_start DATETIME(3) NOT NULL,
    attempts INT UNSIGNED NOT NULL,
    PRIMARY KEY (rate_key)
) ENGINE=InnoDB;

INSERT INTO monitor_accounts(account_key, display_name, account_type, broker_account_id, is_default, enabled, sort_order) VALUES
    ('REAL', 'Real account', 'REAL', '', TRUE, TRUE, 10),
    ('DEMO', 'Demo account', 'DEMO', '', FALSE, TRUE, 20)
ON DUPLICATE KEY UPDATE display_name = VALUES(display_name), account_type = VALUES(account_type), enabled = TRUE;


-- v6 monitoring history, trades and cash flows
CREATE TABLE IF NOT EXISTS strategy_equity_points (
    strategy_key VARCHAR(64) NOT NULL,
    captured_minute DATETIME NOT NULL,
    balance DECIMAL(20, 4) NOT NULL DEFAULT 0,
    equity DECIMAL(20, 4) NOT NULL DEFAULT 0,
    deposit DECIMAL(20, 4) NOT NULL DEFAULT 0,
    current_profit DECIMAL(20, 4) NOT NULL DEFAULT 0,
    position_ticket BIGINT UNSIGNED NULL,
    PRIMARY KEY (strategy_key, captured_minute),
    INDEX idx_equity_strategy_time (strategy_key, captured_minute),
    CONSTRAINT fk_equity_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_market_points (
    strategy_key VARCHAR(64) NOT NULL,
    captured_minute DATETIME NOT NULL,
    current_price DECIMAL(20, 8) NULL,
    bid DECIMAL(20, 8) NULL,
    ask DECIMAL(20, 8) NULL,
    m1_open DECIMAL(20, 8) NULL,
    m1_high DECIMAL(20, 8) NULL,
    m1_low DECIMAL(20, 8) NULL,
    m1_close DECIMAL(20, 8) NULL,
    phase VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (strategy_key, captured_minute),
    INDEX idx_market_strategy_time (strategy_key, captured_minute),
    CONSTRAINT fk_market_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_trades (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    position_ticket BIGINT UNSIGNED NOT NULL,
    symbol VARCHAR(32) NOT NULL DEFAULT '',
    side VARCHAR(8) NOT NULL DEFAULT 'BUY',
    volume DECIMAL(20, 8) NOT NULL DEFAULT 0,
    opened_at DATETIME(3) NOT NULL,
    closed_at DATETIME(3) NULL,
    open_price DECIMAL(20, 8) NOT NULL DEFAULT 0,
    entry_reference_price DECIMAL(20, 8) NULL,
    entry_slippage_points DECIMAL(20, 8) NULL,
    entry_slippage_percent DECIMAL(12, 6) NULL,
    close_price DECIMAL(20, 8) NULL,
    exit_reference_price DECIMAL(20, 8) NULL,
    exit_slippage_points DECIMAL(20, 8) NULL,
    exit_slippage_percent DECIMAL(12, 6) NULL,
    profit DECIMAL(20, 4) NULL,
    profit_percent DECIMAL(12, 6) NULL,
    best_price DECIMAL(20, 8) NULL,
    worst_price DECIMAL(20, 8) NULL,
    mfe_points DECIMAL(20, 8) NULL,
    mfe_percent DECIMAL(12, 6) NULL,
    mae_points DECIMAL(20, 8) NULL,
    mae_percent DECIMAL(12, 6) NULL,
    max_profit DECIMAL(20, 4) NULL,
    max_drawdown DECIMAL(20, 4) NULL,
    exit_reason VARCHAR(100) NOT NULL DEFAULT '',
    balance_before DECIMAL(20, 4) NULL,
    balance_after DECIMAL(20, 4) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_trade_ticket (strategy_key, position_ticket),
    INDEX idx_trade_strategy_opened (strategy_key, opened_at),
    CONSTRAINT fk_trade_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS account_cash_flows (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    occurred_at DATETIME(3) NOT NULL,
    flow_type VARCHAR(32) NOT NULL,
    amount DECIMAL(20, 4) NOT NULL,
    balance_after DECIMAL(20, 4) NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'MANUAL',
    reference_key VARCHAR(100) NULL,
    note VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_cash_flow_reference (strategy_key, reference_key),
    INDEX idx_cash_flow_strategy_time (strategy_key, occurred_at),
    CONSTRAINT fk_cash_flow_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;


-- v7 push notification registration and delivery deduplication
CREATE TABLE IF NOT EXISTS monitor_push_tokens (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    device_id CHAR(32) NOT NULL,
    fcm_token_hash CHAR(64) NOT NULL,
    fcm_token VARCHAR(4096) NOT NULL,
    platform VARCHAR(16) NOT NULL DEFAULT 'ANDROID',
    app_version VARCHAR(32) NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    last_success_at DATETIME(3) NULL,
    last_error VARCHAR(500) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_push_token_hash (fcm_token_hash),
    INDEX idx_push_device_enabled (device_id, enabled),
    CONSTRAINT fk_push_device FOREIGN KEY (device_id) REFERENCES monitor_devices(device_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS monitor_push_deliveries (
    delivery_hash CHAR(64) NOT NULL,
    strategy_key VARCHAR(64) NOT NULL,
    title VARCHAR(120) NOT NULL,
    body VARCHAR(500) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY (delivery_hash),
    INDEX idx_push_delivery_account_time (strategy_key, created_at),
    CONSTRAINT fk_push_delivery_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;


-- v48 global cross-computer role leases, fencing, and weekly-entry idempotency
CREATE TABLE IF NOT EXISTS strategy_runtime_leases (
    strategy_key VARCHAR(64) NOT NULL,
    lease_name VARCHAR(32) NOT NULL,
    owner_id CHAR(32) NOT NULL,
    fencing_token BIGINT UNSIGNED NOT NULL,
    hostname VARCHAR(120) NOT NULL DEFAULT '',
    process_id BIGINT NOT NULL DEFAULT 0,
    build_id VARCHAR(160) NOT NULL DEFAULT '',
    operation_id VARCHAR(96) NOT NULL DEFAULT '',
    operation_kind VARCHAR(64) NOT NULL DEFAULT '',
    acquired_at DATETIME(3) NOT NULL,
    heartbeat_at DATETIME(3) NOT NULL,
    expires_at DATETIME(3) NOT NULL,
    released_at DATETIME(3) NULL,
    metadata JSON NULL,
    PRIMARY KEY (strategy_key, lease_name),
    INDEX idx_runtime_lease_expiry (expires_at),
    CONSTRAINT fk_runtime_lease_account
        FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_weekly_entries (
    strategy_key VARCHAR(64) NOT NULL,
    week_key VARCHAR(10) NOT NULL,
    execution_id VARCHAR(96) NOT NULL,
    decision_id VARCHAR(64) NOT NULL DEFAULT '',
    owner_id CHAR(32) NOT NULL,
    executor_fencing_token BIGINT UNSIGNED NOT NULL,
    gate_fencing_token BIGINT UNSIGNED NOT NULL,
    status VARCHAR(16) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 1,
    claimed_at DATETIME(3) NOT NULL,
    completed_at DATETIME(3) NULL,
    order_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    deal_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    retcode INT NOT NULL DEFAULT -1,
    error_text VARCHAR(500) NOT NULL DEFAULT '',
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (strategy_key, week_key),
    UNIQUE KEY uq_weekly_entry_execution (strategy_key, execution_id),
    INDEX idx_weekly_entry_status (strategy_key, status, updated_at),
    CONSTRAINT fk_weekly_entry_account
        FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

-- v52 two-node Windows supervision and audited mobile desired-state controls
CREATE TABLE IF NOT EXISTS strategy_service_desired_state (
    strategy_key VARCHAR(64) NOT NULL,
    role_name VARCHAR(16) NOT NULL,
    desired_running BOOLEAN NOT NULL DEFAULT TRUE,
    revision BIGINT UNSIGNED NOT NULL DEFAULT 1,
    changed_by_device_id CHAR(32) NULL,
    changed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (strategy_key, role_name),
    CONSTRAINT fk_service_desired_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE,
    CONSTRAINT fk_service_desired_device FOREIGN KEY (changed_by_device_id) REFERENCES monitor_devices(device_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_supervisor_nodes (
    node_role VARCHAR(16) NOT NULL,
    node_id CHAR(32) NOT NULL,
    hostname VARCHAR(120) NOT NULL DEFAULT '',
    process_id BIGINT NOT NULL DEFAULT 0,
    build_id VARCHAR(160) NOT NULL DEFAULT '',
    started_at DATETIME(3) NOT NULL,
    last_seen_at DATETIME(3) NOT NULL,
    process_status JSON NOT NULL,
    PRIMARY KEY (node_role),
    UNIQUE KEY uq_supervisor_node_id (node_id),
    INDEX idx_supervisor_last_seen (last_seen_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_service_control_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    request_id CHAR(32) NOT NULL,
    strategy_key VARCHAR(64) NOT NULL,
    role_name VARCHAR(16) NOT NULL,
    desired_running BOOLEAN NOT NULL,
    device_id CHAR(32) NULL,
    requested_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_service_control_request (request_id),
    INDEX idx_service_control_account_time (strategy_key, requested_at, id),
    CONSTRAINT fk_service_control_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE RESTRICT
) ENGINE=InnoDB;

DROP TRIGGER IF EXISTS strategy_service_control_events_no_update;
DROP TRIGGER IF EXISTS strategy_service_control_events_no_delete;
DELIMITER $$
CREATE TRIGGER strategy_service_control_events_no_update
BEFORE UPDATE ON strategy_service_control_events FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy_service_control_events are immutable';
END$$
CREATE TRIGGER strategy_service_control_events_no_delete
BEFORE DELETE ON strategy_service_control_events FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy_service_control_events are immutable';
END$$
DELIMITER ;

INSERT INTO strategy_service_desired_state(strategy_key, role_name, desired_running)
SELECT a.account_key, roles.role_name, TRUE
  FROM monitor_accounts a
 CROSS JOIN (SELECT 'EXECUTOR' AS role_name UNION ALL SELECT 'PUBLISHER') roles
 WHERE a.enabled = TRUE
ON DUPLICATE KEY UPDATE strategy_key = VALUES(strategy_key);
