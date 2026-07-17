USE oppw_monitor;

CREATE TABLE IF NOT EXISTS monitor_devices (
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

CREATE TABLE IF NOT EXISTS monitor_device_accounts (
    device_id CHAR(32) NOT NULL,
    account_key VARCHAR(64) NOT NULL,
    PRIMARY KEY (device_id, account_key),
    CONSTRAINT fk_device_accounts_device FOREIGN KEY (device_id) REFERENCES monitor_devices(device_id) ON DELETE CASCADE,
    CONSTRAINT fk_device_accounts_account FOREIGN KEY (account_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS monitor_access_tokens (
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

CREATE TABLE IF NOT EXISTS monitor_pairing_codes (
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

CREATE TABLE IF NOT EXISTS monitor_pairing_code_accounts (
    pairing_code_id BIGINT UNSIGNED NOT NULL,
    account_key VARCHAR(64) NOT NULL,
    PRIMARY KEY (pairing_code_id, account_key),
    CONSTRAINT fk_pair_code_accounts_code FOREIGN KEY (pairing_code_id) REFERENCES monitor_pairing_codes(id) ON DELETE CASCADE,
    CONSTRAINT fk_pair_code_accounts_account FOREIGN KEY (account_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS auth_rate_limits (
    rate_key CHAR(64) NOT NULL,
    window_start DATETIME(3) NOT NULL,
    attempts INT UNSIGNED NOT NULL,
    PRIMARY KEY (rate_key)
) ENGINE=InnoDB;
