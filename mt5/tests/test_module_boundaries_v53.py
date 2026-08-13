from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import sys
import types
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    mt5.ORDER_TYPE_BUY = 0
    mt5.ORDER_TYPE_SELL = 1
    mt5.POSITION_TYPE_BUY = 0
    mt5.POSITION_TYPE_SELL = 1
    mt5.ACCOUNT_TRADE_MODE_DEMO = 0
    mt5.ACCOUNT_TRADE_MODE_REAL = 2
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
    spec = importlib.util.spec_from_file_location("oppw_v53_module_boundary_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()


class ModuleBoundaryTests(unittest.TestCase):
    def test_canonical_entrypoint_is_thin_composition_root(self):
        source = Path(MODULE.__file__).read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 600)
        self.assertIn("class OPPWContinuousStrategy(", source)
        self.assertNotIn("class BackendLeaseCoordinator", source)
        self.assertNotIn("class MobileMonitorPublisher", source)

    def test_named_account_type_must_match_the_connected_mt5_trade_mode(self):
        self.assertTrue(MODULE.account_trade_mode_matches("DEMO", 0))
        self.assertTrue(MODULE.account_trade_mode_matches("REAL", 2))
        self.assertFalse(MODULE.account_trade_mode_matches("DEMO", 2))
        self.assertFalse(MODULE.account_trade_mode_matches("REAL", 0))
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.account_type = "DEMO"
        strategy.cfg = SimpleNamespace(login=123)
        with patch.object(
            MODULE.mt5,
            "account_info",
            return_value=SimpleNamespace(login=123, trade_mode=2),
            create=True,
        ):
            self.assertFalse(strategy.selected_account_matches())

    def test_named_account_cli_preserves_legacy_default_and_accepts_a_key(self):
        legacy = MODULE.parse_arguments(["--account", "demo"])
        named = MODULE.parse_arguments(["--account", "real", "--account-key", "REAL_PROP"])
        self.assertEqual("", legacy.account_key)
        self.assertEqual("real", named.account)
        self.assertEqual("REAL_PROP", named.account_key)

    def test_connect_forwards_configured_initialize_timeout_in_milliseconds(self):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.account = "DEMO_TMS"
        strategy.cfg = SimpleNamespace(
            terminal_path=r"D:\oppw\mt5\demo_tms\MetaTrader 5\terminal64.exe",
            login=123,
            password="password",
            server="server",
            mt5_initialize_timeout_seconds=120.0,
            separate_mt5_login_after_initialize=False,
            auto_acknowledge_high_risk_warning=False,
        )
        with patch.object(MODULE.mt5, "initialize", return_value=False, create=True) as initialize, patch.object(
            MODULE.mt5, "last_error", return_value=(-10005, "IPC timeout"), create=True
        ):
            with self.assertRaisesRegex(RuntimeError, "IPC timeout"):
                strategy.connect()
        initialize.assert_called_once_with(
            strategy.cfg.terminal_path,
            login=123,
            password="password",
            server="server",
            timeout=120000,
        )

    def test_tms_two_phase_connect_attaches_before_broker_login(self):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.account = "DEMO_TMS"
        strategy.cfg = SimpleNamespace(
            terminal_path=r"D:\oppw\mt5\demo_tms\MetaTrader 5\terminal64.exe",
            login=123,
            password="password",
            server="server",
            mt5_initialize_timeout_seconds=120.0,
            separate_mt5_login_after_initialize=True,
            auto_acknowledge_high_risk_warning=False,
        )
        strategy.log = Mock()
        with patch.object(MODULE.mt5, "initialize", return_value=True, create=True) as initialize, patch.object(
            MODULE.mt5, "login", return_value=False, create=True
        ) as login, patch.object(
            MODULE.mt5, "last_error", return_value=(-6, "authorization failed"), create=True
        ), patch.object(MODULE.mt5, "shutdown", create=True) as shutdown:
            with self.assertRaisesRegex(RuntimeError, "authorization failed"):
                strategy.connect()

        initialize.assert_called_once_with(strategy.cfg.terminal_path, timeout=120000)
        login.assert_called_once_with(123, password="password", server="server", timeout=120000)
        shutdown.assert_called_once_with()

    def test_strategy_methods_are_owned_by_cohesive_modules(self):
        strategy = MODULE.OPPWContinuousStrategy
        expected = {
            "session_times": "oppw_core.session_calendar",
            "recover_position_state": "oppw_core.position_lifecycle",
            "strategy_decision_payload": "oppw_core.strategy_decision",
            "build_mobile_snapshot": "oppw_core.monitoring",
            "send_buy": "oppw_core.broker_execution",
            "run_executor": "oppw_core.runtime",
        }
        for method_name, owner in expected.items():
            with self.subTest(method=method_name):
                self.assertEqual(owner, getattr(strategy, method_name).__module__)

    def test_canonical_module_preserves_established_public_surface(self):
        for name in (
            "BackendLeaseCoordinator",
            "CoordinationError",
            "M1Bar",
            "OPPWContinuousStrategy",
            "SessionTimes",
            "StrategyState",
            "TradeExecutionGate",
            "main",
            "mt5",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(MODULE, name))
        self.assertEqual(
            "(self, position, reason: 'str', now: 'datetime') -> 'bool'",
            str(inspect.signature(MODULE.OPPWContinuousStrategy.close_position_market)),
        )

    def test_only_core_connection_methods_remain_on_composition_class(self):
        own_methods = {
            name
            for name, value in MODULE.OPPWContinuousStrategy.__dict__.items()
            if inspect.isfunction(value)
        }
        self.assertEqual(
            {
                "__init__",
                "autotrading_status",
                "connect",
                "connection_healthy",
                "disconnect",
                "ensure_autotrading_enabled",
                "print_autotrading_banner",
                "print_instance_banner",
                "print_live_enabled_banner",
                "selected_account_matches",
            },
            own_methods,
        )


if __name__ == "__main__":
    unittest.main()
