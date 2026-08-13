from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DataLifecycleStaticTests(unittest.TestCase):
    def test_forward_migration_is_last_and_protects_market_minutes(self):
        order = [
            line.strip()
            for line in (ROOT / "Mobile/backend/sql/migration-order.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertLess(order.index("migrate_data_lifecycle.sql"), order.index("migrate_v55_entry_rules.sql"))
        self.assertLess(
            order.index("migrate_v56_2_execution_lifecycle_links.sql"),
            order.index("migrate_v56_2_bossa_tms_accounts.sql"),
        )
        self.assertEqual(order[-1], "migrate_v56_2_bossa_tms_accounts.sql")
        accounts = (ROOT / "Mobile/backend/sql/migrate_v56_2_bossa_tms_accounts.sql").read_text(encoding="utf-8")
        for marker in ("DEMO BOSSA", "REAL BOSSA", "DEMO_TMS", "REAL_TMS", "FALSE, FALSE"):
            self.assertIn(marker, accounts)
        migration = (ROOT / "Mobile/backend/sql/migrate_data_lifecycle.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS strategy_equity_daily", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS strategy_retention_runs", migration)
        self.assertIn("CREATE TRIGGER strategy_market_points_no_delete", migration)
        self.assertIn("retained indefinitely", migration)
        self.assertIn("idx_event_retention_time", migration)
        self.assertIn("idx_equity_retention_time", migration)
        self.assertIn("ON DELETE RESTRICT", migration)

    def test_retention_has_only_the_two_authorized_deletion_paths(self):
        source = (ROOT / "Mobile/backend/admin/retention.php").read_text(encoding="utf-8")
        deleted_tables = {
            match.group(1).lower()
            for match in re.finditer(r"DELETE\s+FROM\s+`?([a-z0-9_]+)", source, re.IGNORECASE)
        }
        self.assertEqual(deleted_tables, {"strategy_events", "strategy_equity_points"})
        self.assertIn("name <> 'EXECUTION_STAGE'", source)
        self.assertIn("OPPW_EVENT_RETENTION_DAYS = 180", source)
        self.assertIn("OPPW_EQUITY_RETENTION_DAYS = 400", source)
        self.assertIn("OPPW_EVENT_RETENTION_DAYS, OPPW_EVENT_RETENTION_DAYS", source)
        self.assertIn("OPPW_EQUITY_RETENTION_DAYS, OPPW_EQUITY_RETENTION_DAYS", source)
        self.assertIn("PHP_SAPI !== 'cli'", source)
        self.assertIn("GET_LOCK", source)
        self.assertIn("hash_file('sha256'", source)

    def test_retained_equity_is_read_by_status_and_analytics(self):
        status = (ROOT / "Mobile/backend/status.php").read_text(encoding="utf-8")
        analytics = (ROOT / "Mobile/backend/analytics.php").read_text(encoding="utf-8")
        self.assertIn("strategy_equity_daily", status)
        self.assertIn("close_equity AS equity", status)
        self.assertIn("strategy_equity_daily", analytics)
        self.assertIn("UNION ALL", analytics)

    def test_recovery_drill_uses_two_disposable_databases_and_checks_authority(self):
        source = (ROOT / "tools/validate_backup_restore.ps1").read_text(encoding="utf-8")
        for marker in (
            "$sourceContainer", "$restoreContainer", "--single-transaction", "--routines",
            "--triggers", "strategy_specifications", "strategy_account_spec_assignments",
            "strategy_decisions", "strategy_execution_stages", "strategy_fills",
            "strategy_protection_changes", "strategy_trade_ledger", "account_cash_flows",
            "strategy_service_control_events", "strategy_entry_rule_control_events",
            "strategy_entry_rule_week_state", "strategy_entry_rule_week_events", "strategy_market_points",
        ):
            self.assertIn(marker, source)
        self.assertIn("Get-TableDigest", source)
        self.assertIn("Assert-MutationRejected", source)

    def test_production_backup_is_encrypted_scheduled_and_restore_verified(self):
        source = (ROOT / "tools/backup_mysql.ps1").read_text(encoding="utf-8")
        installer = (ROOT / "tools/install_mysql_backup_task.ps1").read_text(encoding="utf-8")
        helper = (ROOT / "tools/write_mysql_client_config.php").read_text(encoding="utf-8")
        for marker in (
            "--single-transaction", "--routines", "--triggers", "TLS_REQUIRED", "tls=required",
            "Restore-And-Verify", "WINDOWS_EFS", "Start-Transcript", "KeepDaily = 35",
            "KeepMonthly = 12", "KeepLogDays = 180", "strategy_market_points",
            "strategy_service_control_events",
            "strategy_entry_rule_week_events",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("--password=", source)
        self.assertIn("@($final, ($final + '.sha256'), ($final + '.json'))", source)
        self.assertIn("$process.ExitCode -eq 0 -and $port.Trim() -eq '3306'", source)
        for marker in (
            "OPPW MySQL Production Backup", "D:\\OPPW-Backups\\mysql", "02:15",
            "New-ScheduledTaskTrigger -Daily", "LogonType Interactive", "RunOnlyIfNetworkAvailable",
        ):
            self.assertIn(marker, installer)
        self.assertIn("password=' . $quote($password)", helper)
        self.assertIn("ssl-mode=REQUIRED", helper)
        self.assertNotIn("db_password' =>", helper)


if __name__ == "__main__":
    unittest.main()
