DROP PROCEDURE IF EXISTS oppw_v52_add_service_control_column;
DELIMITER $$
CREATE PROCEDURE oppw_v52_add_service_control_column(IN table_name_value VARCHAR(64))
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = table_name_value AND COLUMN_NAME = 'can_control_service'
    ) THEN
        SET @sql_text = CONCAT(
            'ALTER TABLE ', table_name_value,
            ' ADD COLUMN can_control_service BOOLEAN NOT NULL DEFAULT FALSE'
        );
        PREPARE statement_value FROM @sql_text;
        EXECUTE statement_value;
        DEALLOCATE PREPARE statement_value;
    END IF;
END$$
DELIMITER ;

CALL oppw_v52_add_service_control_column('monitor_pairing_code_accounts');
CALL oppw_v52_add_service_control_column('monitor_device_accounts');
DROP PROCEDURE oppw_v52_add_service_control_column;

CREATE TABLE IF NOT EXISTS strategy_service_desired_state (
    strategy_key VARCHAR(64) NOT NULL,
    role_name VARCHAR(16) NOT NULL,
    desired_running BOOLEAN NOT NULL DEFAULT TRUE,
    revision BIGINT UNSIGNED NOT NULL DEFAULT 1,
    changed_by_device_id CHAR(32) NULL,
    changed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (strategy_key, role_name),
    CONSTRAINT fk_service_desired_account
        FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE,
    CONSTRAINT fk_service_desired_device
        FOREIGN KEY (changed_by_device_id) REFERENCES monitor_devices(device_id) ON DELETE SET NULL
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
    CONSTRAINT fk_service_control_account
        FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE RESTRICT
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
