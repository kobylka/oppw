-- OPPW Monitor v7 migration. Run once after migrate_v6.sql.

ALTER TABLE strategy_trades
    ADD COLUMN entry_reference_price DECIMAL(20,8) NULL AFTER open_price,
    ADD COLUMN entry_slippage_points DECIMAL(20,8) NULL AFTER entry_reference_price,
    ADD COLUMN entry_slippage_percent DECIMAL(12,6) NULL AFTER entry_slippage_points,
    ADD COLUMN exit_reference_price DECIMAL(20,8) NULL AFTER close_price,
    ADD COLUMN exit_slippage_points DECIMAL(20,8) NULL AFTER exit_reference_price,
    ADD COLUMN exit_slippage_percent DECIMAL(12,6) NULL AFTER exit_slippage_points,
    ADD COLUMN best_price DECIMAL(20,8) NULL AFTER profit_percent,
    ADD COLUMN worst_price DECIMAL(20,8) NULL AFTER best_price,
    ADD COLUMN mfe_points DECIMAL(20,8) NULL AFTER worst_price,
    ADD COLUMN mfe_percent DECIMAL(12,6) NULL AFTER mfe_points,
    ADD COLUMN mae_points DECIMAL(20,8) NULL AFTER mfe_percent,
    ADD COLUMN mae_percent DECIMAL(12,6) NULL AFTER mae_points,
    ADD COLUMN max_profit DECIMAL(20,4) NULL AFTER mae_percent,
    ADD COLUMN max_drawdown DECIMAL(20,4) NULL AFTER max_profit;

ALTER TABLE strategy_events
    ADD COLUMN event_hash CHAR(64) NULL AFTER details,
    ADD UNIQUE KEY uq_strategy_event_hash(strategy_key, event_hash),
    ADD INDEX idx_event_strategy_id(strategy_key, id),
    ADD INDEX idx_event_strategy_name(strategy_key, name, id);

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
    UNIQUE KEY uq_push_token_hash(fcm_token_hash),
    INDEX idx_push_device_enabled(device_id, enabled),
    CONSTRAINT fk_push_device FOREIGN KEY(device_id) REFERENCES monitor_devices(device_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS monitor_push_deliveries (
    delivery_hash CHAR(64) NOT NULL,
    strategy_key VARCHAR(64) NOT NULL,
    title VARCHAR(120) NOT NULL,
    body VARCHAR(500) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY(delivery_hash),
    INDEX idx_push_delivery_account_time(strategy_key, created_at),
    CONSTRAINT fk_push_delivery_account FOREIGN KEY(strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;
