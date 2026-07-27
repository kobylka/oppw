from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
import sys
import types
import unittest


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    mt5.ORDER_TYPE_BUY = 0
    mt5.ORDER_TYPE_SELL = 1
    mt5.POSITION_TYPE_BUY = 0
    mt5.POSITION_TYPE_SELL = 1
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
