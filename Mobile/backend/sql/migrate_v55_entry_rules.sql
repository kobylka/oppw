CREATE TABLE IF NOT EXISTS strategy_entry_rule_controls (
    strategy_key VARCHAR(64) NOT NULL,
    arithmetic_last_two_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    gap_momentum_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    tuesday_normalization_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    premarket_range_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    premarket_close_low_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    revision BIGINT UNSIGNED NOT NULL DEFAULT 1,
    changed_by_device_id CHAR(32) NULL,
    changed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (strategy_key),
    CONSTRAINT fk_entry_rule_controls_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE,
    CONSTRAINT fk_entry_rule_controls_device FOREIGN KEY (changed_by_device_id) REFERENCES monitor_devices(device_id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_entry_rule_control_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    request_id CHAR(32) NOT NULL,
    strategy_key VARCHAR(64) NOT NULL,
    rule_key VARCHAR(48) NOT NULL,
    enabled BOOLEAN NOT NULL,
    device_id CHAR(32) NULL,
    requested_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_entry_rule_control_request (request_id),
    INDEX idx_entry_rule_control_account_time (strategy_key, requested_at, id),
    CONSTRAINT fk_entry_rule_control_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_entry_rule_week_state (
    strategy_key VARCHAR(64) NOT NULL,
    week_key VARCHAR(10) NOT NULL,
    status VARCHAR(48) NOT NULL,
    revision BIGINT UNSIGNED NOT NULL DEFAULT 1,
    controls_revision BIGINT UNSIGNED NOT NULL,
    decision_id VARCHAR(64) NOT NULL DEFAULT '',
    inputs JSON NOT NULL,
    changed_at DATETIME(3) NOT NULL,
    PRIMARY KEY (strategy_key, week_key),
    INDEX idx_entry_rule_week_status (strategy_key, status, week_key),
    CONSTRAINT fk_entry_rule_week_state_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_entry_rule_week_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    request_id CHAR(32) NOT NULL,
    strategy_key VARCHAR(64) NOT NULL,
    week_key VARCHAR(10) NOT NULL,
    status VARCHAR(48) NOT NULL,
    controls_revision BIGINT UNSIGNED NOT NULL,
    decision_id VARCHAR(64) NOT NULL DEFAULT '',
    owner_id CHAR(32) NOT NULL,
    fencing_token BIGINT UNSIGNED NOT NULL,
    inputs JSON NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    recorded_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_entry_rule_week_request (request_id),
    INDEX idx_entry_rule_week_event_account_time (strategy_key, recorded_at, id),
    CONSTRAINT fk_entry_rule_week_event_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE RESTRICT
) ENGINE=InnoDB;

DROP TRIGGER IF EXISTS strategy_entry_rule_control_events_no_update;
DROP TRIGGER IF EXISTS strategy_entry_rule_control_events_no_delete;
DROP TRIGGER IF EXISTS strategy_entry_rule_week_events_no_update;
DROP TRIGGER IF EXISTS strategy_entry_rule_week_events_no_delete;
DELIMITER $$
CREATE TRIGGER strategy_entry_rule_control_events_no_update
BEFORE UPDATE ON strategy_entry_rule_control_events FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy_entry_rule_control_events are immutable';
END$$
CREATE TRIGGER strategy_entry_rule_control_events_no_delete
BEFORE DELETE ON strategy_entry_rule_control_events FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy_entry_rule_control_events are immutable';
END$$
CREATE TRIGGER strategy_entry_rule_week_events_no_update
BEFORE UPDATE ON strategy_entry_rule_week_events FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy_entry_rule_week_events are immutable';
END$$
CREATE TRIGGER strategy_entry_rule_week_events_no_delete
BEFORE DELETE ON strategy_entry_rule_week_events FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy_entry_rule_week_events are immutable';
END$$
DELIMITER ;

INSERT INTO strategy_entry_rule_controls(strategy_key)
SELECT account_key FROM monitor_accounts WHERE enabled=TRUE
ON DUPLICATE KEY UPDATE strategy_key=VALUES(strategy_key);
