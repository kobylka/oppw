-- Merge the two legacy premarket switches into the single PREMARKET_LOW rule.
-- Existing intent is preserved conservatively: the merged rule is enabled only
-- when both legacy prerequisites were enabled.
SET @oppw_has_premarket_low := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'strategy_entry_rule_controls'
       AND COLUMN_NAME = 'premarket_low_enabled'
);
SET @oppw_has_premarket_range := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'strategy_entry_rule_controls'
       AND COLUMN_NAME = 'premarket_range_enabled'
);
SET @oppw_has_premarket_close := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'strategy_entry_rule_controls'
       AND COLUMN_NAME = 'premarket_close_low_enabled'
);

SET @oppw_sql := IF(
    @oppw_has_premarket_low = 0 AND @oppw_has_premarket_range = 1 AND @oppw_has_premarket_close = 1,
    'UPDATE strategy_entry_rule_controls SET premarket_range_enabled = (premarket_range_enabled AND premarket_close_low_enabled)',
    'SELECT 1'
);
PREPARE oppw_statement FROM @oppw_sql;
EXECUTE oppw_statement;
DEALLOCATE PREPARE oppw_statement;

SET @oppw_sql := IF(
    @oppw_has_premarket_low = 0 AND @oppw_has_premarket_range = 1,
    'ALTER TABLE strategy_entry_rule_controls CHANGE COLUMN premarket_range_enabled premarket_low_enabled BOOLEAN NOT NULL DEFAULT TRUE',
    'SELECT 1'
);
PREPARE oppw_statement FROM @oppw_sql;
EXECUTE oppw_statement;
DEALLOCATE PREPARE oppw_statement;

SET @oppw_sql := IF(
    @oppw_has_premarket_close = 1,
    'ALTER TABLE strategy_entry_rule_controls DROP COLUMN premarket_close_low_enabled',
    'SELECT 1'
);
PREPARE oppw_statement FROM @oppw_sql;
EXECUTE oppw_statement;
DEALLOCATE PREPARE oppw_statement;
