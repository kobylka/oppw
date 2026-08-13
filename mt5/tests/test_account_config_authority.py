from __future__ import annotations

import importlib.util
import sys
import tempfile
from dataclasses import fields
from pathlib import Path
import unittest


MT5_DIR = Path(__file__).resolve().parents[1]
ROOT = MT5_DIR.parent
if str(MT5_DIR) not in sys.path:
    sys.path.insert(0, str(MT5_DIR))

from oppw_core.account_config import (  # noqa: E402
    CONFIG_FIELD_NAMES,
    account_config_path,
    build_account_config,
    default_config,
    effective_config_summary,
    load_private_overrides,
    normalize_account_key,
    scope_config_to_account,
)
from oppw_core.settings import Config  # noqa: E402


def load_migration_module():
    source = ROOT / "tools" / "migrate_mt5_config.py"
    spec = importlib.util.spec_from_file_location("oppw_config_migration_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = load_migration_module()


class AccountConfigAuthorityTests(unittest.TestCase):
    def test_canonical_schema_is_the_field_authority(self):
        self.assertEqual(tuple(field.name for field in fields(Config)), CONFIG_FIELD_NAMES)
        example = (MT5_DIR / "oppw_mt5_config.example.py").read_text(encoding="utf-8")
        self.assertNotIn("class Config", example)
        self.assertNotIn("def env_", example)
        self.assertIn("OVERRIDES = {", example)

    def test_precedence_is_defaults_then_private_then_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            account_dir = Path(directory)
            private = {
                "terminal_path": "private-terminal",
                "login": 123,
                "password": "private-password",
                "server": "private-server",
                "monitor_write_token": "private-token",
                "poll_seconds": 0.4,
                "auto_acknowledge_high_risk_warning": True,
                "live_enabled": False,
            }
            config = build_account_config(
                "DEMO",
                account_dir,
                private,
                environ={"OPPW_POLL_SECONDS": "0.7", "OPPW_LIVE": "1"},
            )
            self.assertEqual(0.7, config.poll_seconds)
            self.assertTrue(config.live_enabled)
            self.assertTrue(config.auto_acknowledge_high_risk_warning)
            self.assertEqual(123, config.login)
            self.assertEqual(account_dir / "oppw_mt5_state.json", config.state_file)

    def test_named_accounts_have_distinct_files_identities_paths_and_strategy_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            mt5 = Path(directory)
            account_dir = mt5 / "demo"
            alpha = build_account_config(
                "DEMO_ALPHA",
                account_dir,
                {"base_leverage": 8, "required_balance_multiplier": 1.765, "login": 101},
                environ={},
            )
            beta = build_account_config(
                "DEMO_BETA",
                account_dir,
                {
                    "base_leverage": 10,
                    "required_balance_multiplier": 1.5,
                    "trade_symbol": "US100.pro",
                    "signal_symbol": "US100.pro",
                    "market_order_priority_delay_seconds": 0.5,
                    "login": 202,
                },
                environ={},
            )
            alpha = scope_config_to_account(alpha, "DEMO_ALPHA")
            beta = scope_config_to_account(beta, "DEMO_BETA")

            self.assertEqual(mt5 / "demo" / "demo_mt5_config.py", account_config_path("DEMO", "DEMO", mt5))
            self.assertEqual(
                mt5 / "demo" / "demo_alpha_mt5_config.py",
                account_config_path("demo", "demo_alpha", mt5),
            )
            self.assertEqual("DEMO_ALPHA", alpha.monitor_account_key)
            self.assertEqual("DEMO_BETA", beta.monitor_account_key)
            self.assertEqual(8, alpha.base_leverage)
            self.assertEqual(10, beta.base_leverage)
            self.assertEqual(1.765, alpha.required_balance_multiplier)
            self.assertEqual(1.5, beta.required_balance_multiplier)
            self.assertEqual("US100", alpha.trade_symbol)
            self.assertEqual("US100.pro", beta.trade_symbol)
            self.assertEqual("US100.pro", beta.signal_symbol)
            self.assertEqual(0.5, beta.market_order_priority_delay_seconds)
            self.assertNotEqual(alpha.state_file, beta.state_file)
            self.assertNotEqual(alpha.log_dir, beta.log_dir)

    def test_account_keys_are_strict_and_account_scoping_is_idempotent(self):
        with self.assertRaisesRegex(RuntimeError, "Account key"):
            normalize_account_key("demo alpha")
        with self.assertRaisesRegex(RuntimeError, "Reserved account key"):
            account_config_path("REAL", "DEMO", Path("mt5"))
        config = scope_config_to_account(
            Config(
                state_file=Path("state.demo_alpha.json"),
                monitor_history_file=Path("history.demo_alpha.json"),
                log_dir=Path("logs/demo_alpha"),
            ),
            "DEMO_ALPHA",
        )
        self.assertEqual(Path("state.demo_alpha.json"), config.state_file)
        self.assertEqual(Path("history.demo_alpha.json"), config.monitor_history_file)
        self.assertEqual(Path("logs/demo_alpha"), config.log_dir)

    def test_private_config_rejects_unknown_fields_and_copied_config_class(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.py"
            path.write_text(
                "MT5_TERMINAL_PATH=''\nMT5_LOGIN=0\nMT5_PASSWORD=''\n"
                "MT5_SERVER=''\nMONITOR_WRITE_TOKEN=''\nOVERRIDES={'unknown': 1}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "Unknown private configuration fields"):
                load_private_overrides(path)
            path.write_text("class Config:\n    pass\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "still defines Config"):
                load_private_overrides(path)

    def test_effective_summary_never_contains_secrets(self):
        summary = effective_config_summary(
            Config(password="secret-password", monitor_write_token="secret-token")
        )
        self.assertNotIn("password", summary)
        self.assertNotIn("monitor_write_token", summary)
        self.assertEqual("US100", summary["trade_symbol"])

    def test_legacy_private_config_is_migrated_without_value_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            mt5 = repo / "mt5"
            account_dir = mt5 / "demo"
            account_dir.mkdir(parents=True)
            # The migration imports the repository's canonical package. A junction
            # is not portable in tests, so point sys.path at the real canonical mt5.
            sys.path.insert(0, str(MT5_DIR))
            try:
                path = account_dir / "demo_mt5_config.py"
                path.write_text(
                    "from dataclasses import replace\n"
                    "from pathlib import Path\n"
                    "from oppw_core.settings import Config as CanonicalConfig\n"
                    f"BASE = Path({str(account_dir)!r})\n"
                    "class Config:\n"
                    "    def __new__(cls):\n"
                    "        return replace(CanonicalConfig(), config_name='DEMO', "
                    "monitor_account_key='DEMO', terminal_path='terminal', login=123, "
                    "password='password', server='server', monitor_write_token='token', "
                    "poll_seconds=0.35, state_file=BASE/'state.json', log_dir=BASE/'logs', "
                    "monitor_history_file=BASE/'history.json')\n",
                    encoding="utf-8",
                )
                changed = MIGRATION.migrate_file(repo, "DEMO", path)
                self.assertTrue(changed)
                migrated_source = path.read_text(encoding="utf-8")
                self.assertNotIn("class Config", migrated_source)
                private = load_private_overrides(path)
                config = build_account_config("DEMO", account_dir, private, environ={})
                self.assertEqual(123, config.login)
                self.assertEqual(0.35, config.poll_seconds)
                self.assertEqual(account_dir / "state.json", config.state_file)
                self.assertFalse(MIGRATION.migrate_file(repo, "DEMO", path))
            finally:
                sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
