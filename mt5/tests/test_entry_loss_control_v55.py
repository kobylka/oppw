from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    mt5.ORDER_TYPE_BUY = 0
    mt5.ORDER_TYPE_SELL = 1
    mt5.POSITION_TYPE_BUY = 0
    mt5.POSITION_TYPE_SELL = 1
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
    spec = importlib.util.spec_from_file_location("oppw_v55_entry_rules_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()
WARSAW = ZoneInfo("Europe/Warsaw")
MONDAY = date(2026, 8, 10)
TUESDAY = date(2026, 8, 11)


class EntryLossControlTests(unittest.TestCase):
    def strategy(self):
        strategy = object.__new__(MODULE.OPPWContinuousStrategy)
        strategy.cfg = SimpleNamespace(
            entry_rule_arithmetic_threshold=0.02,
            entry_rule_gap_threshold=0.01,
            entry_rule_momentum20_threshold=-0.005,
            entry_rule_tuesday_normalization_tolerance=0.005,
            entry_rule_premarket_minimum_range=0.008,
            entry_rule_premarket_maximum_close_location=0.15,
            entry_window_seconds=55,
        )
        strategy.entry_rule_controls_revision = 3
        strategy.entry_rule_controls = {
            "ARITHMETIC_LAST_TWO": True,
            "GAP_MOMENTUM": True,
            "TUESDAY_NORMALIZATION": True,
            "PREMARKET_LOW": True,
        }
        return strategy

    @staticmethod
    def backend(outcomes):
        return {
            "recentOutcomes": [
                {"weekKey": f"2026-W{31 - index:02d}", "return": value, "source": "test"}
                for index, value in enumerate(outcomes)
            ]
        }

    @staticmethod
    def quiet_market():
        return {
            "cashOpen": 100.0,
            "previousCashClose": 100.0,
            "momentum20": 0.01,
            "premarketOpen": 100.0,
            "premarketHigh": 100.4,
            "premarketLow": 99.9,
            "premarketClose": 100.2,
            "premarketBars": 930,
        }

    def test_last_two_outcomes_use_arithmetic_sum_and_have_priority(self):
        strategy = self.strategy()
        market = self.quiet_market() | {
            "cashOpen": 101.0,
            "previousCashClose": 100.0,
            "momentum20": -0.005,
            "premarketHigh": 100.8,
            "premarketLow": 100.0,
            "premarketClose": 100.12,
        }
        status, inputs = strategy.loss_control_entry_decision(MONDAY, self.backend([-0.011, -0.010]), market)
        self.assertEqual("SKIP_ARITHMETIC", status)
        self.assertAlmostEqual(-0.021, inputs["arithmeticSum"])

    def test_gap_and_momentum_are_one_combined_rule(self):
        strategy = self.strategy()
        strategy.entry_rule_controls["PREMARKET_LOW"] = False
        market = self.quiet_market() | {"cashOpen": 101.0, "momentum20": -0.005}
        status, _ = strategy.loss_control_entry_decision(MONDAY, self.backend([0.0, 0.0]), market)
        self.assertEqual("DEFER_TUESDAY", status)
        market["momentum20"] = -0.0049
        self.assertEqual("ENTER", strategy.loss_control_entry_decision(MONDAY, self.backend([0.0, 0.0]), market)[0])
        strategy.entry_rule_controls["GAP_MOMENTUM"] = False
        market["momentum20"] = -0.02
        self.assertEqual("ENTER", strategy.loss_control_entry_decision(MONDAY, self.backend([0.0, 0.0]), market)[0])

    def test_holiday_tuesday_gap_momentum_skips_without_another_defer(self):
        strategy = self.strategy()
        strategy.entry_rule_controls["PREMARKET_LOW"] = False
        market = self.quiet_market() | {"cashOpen": 101.0, "momentum20": -0.005}
        self.assertEqual(
            "SKIP_GAP_MOMENTUM",
            strategy.loss_control_entry_decision(TUESDAY, self.backend([0.0, 0.0]), market)[0],
        )

    def test_premarket_skip_is_one_control_requiring_both_thresholds(self):
        strategy = self.strategy()
        strategy.entry_rule_controls["GAP_MOMENTUM"] = False
        market = self.quiet_market() | {
            "premarketOpen": 100.0,
            "premarketHigh": 100.8,
            "premarketLow": 100.0,
            "premarketClose": 100.12,
        }
        self.assertEqual("SKIP_PREMARKET_LOW", strategy.loss_control_entry_decision(MONDAY, self.backend([0.0, 0.0]), market)[0])
        strategy.entry_rule_controls["PREMARKET_LOW"] = False
        self.assertEqual("ENTER", strategy.loss_control_entry_decision(MONDAY, self.backend([0.0, 0.0]), market)[0])
        strategy.entry_rule_controls["PREMARKET_LOW"] = True
        market["premarketHigh"] = 100.79
        self.assertEqual("ENTER", strategy.loss_control_entry_decision(MONDAY, self.backend([0.0, 0.0]), market)[0])
        market["premarketHigh"] = 100.8
        market["premarketClose"] = 100.121
        self.assertEqual("ENTER", strategy.loss_control_entry_decision(MONDAY, self.backend([0.0, 0.0]), market)[0])

    def test_tuesday_normalization_is_symmetric_from_friday(self):
        strategy = self.strategy()
        self.assertTrue(strategy.normalized_tuesday_entry_rule(100.0, 100.5))
        self.assertTrue(strategy.normalized_tuesday_entry_rule(100.0, 99.5))
        self.assertFalse(strategy.normalized_tuesday_entry_rule(100.0, 100.51))
        self.assertFalse(strategy.normalized_tuesday_entry_rule(100.0, 99.49))

    def test_backend_context_refresh_is_cached_at_monitor_cadence(self):
        strategy = self.strategy()
        strategy.last_entry_rule_context = None
        strategy.last_entry_rule_context_monotonic = 0.0
        calls = []
        payload = {
            "ok": True,
            "revision": 3,
            "rules": [
                {"key": key, "enabled": enabled}
                for key, enabled in strategy.entry_rule_controls.items()
            ],
            "weekState": None,
            "recentOutcomes": [],
        }
        strategy.entry_rule_backend_request = lambda _day: calls.append(True) or payload
        self.assertIs(payload, strategy.refresh_entry_rule_context(MONDAY))
        self.assertIs(payload, strategy.refresh_entry_rule_context(MONDAY))
        self.assertEqual(1, len(calls))

    def test_loop_does_not_poll_controls_before_entry_context_lead(self):
        strategy = self.strategy()
        strategy.state = MODULE.StrategyState()
        strategy.exit_latched_reason = ""
        cash_open = datetime.combine(MONDAY, time(15, 30), WARSAW)
        buy_action = cash_open - timedelta(seconds=3)
        strategy.session_times = lambda _day: SimpleNamespace(buy_action=buy_action, cash_open=cash_open)
        strategy.refresh_entry_rule_context = lambda _day: self.fail("controls must not be polled this early")
        strategy.maybe_open_new_week(MONDAY, buy_action - timedelta(seconds=6), None, None)

    def test_loop_records_arithmetic_skip_without_sending_buy(self):
        strategy = self.strategy()
        strategy.state = MODULE.StrategyState()
        strategy.state.entry_pending_until_utc = 0
        strategy.exit_latched_reason = ""
        strategy.last_entry_rule_error_monotonic = 0.0
        strategy.cfg.monitor_error_log_interval_seconds = 30.0
        strategy.refresh_entry_rule_context = lambda _day: self.backend([-0.011, -0.010]) | {"weekState": None}
        strategy.is_new_week_entry = lambda _day: True
        cash_open = datetime.combine(MONDAY, time(15, 30), WARSAW)
        strategy.session_times = lambda _day: SimpleNamespace(
            buy_action=cash_open.replace(second=0) , cash_open=cash_open,
        )
        strategy.previous_trading_date = lambda _day: date(2026, 8, 7)
        strategy.refresh_previous_full_week_change = lambda _day: None
        strategy.entry_rule_market_context = lambda _day: self.quiet_market()
        recorded = []
        strategy.record_entry_rule_week_state = lambda _day, status, inputs: recorded.append((status, inputs)) or {}
        strategy.remember_entry_rule_decision = lambda *_args: None
        strategy.send_buy = lambda *_args, **_kwargs: self.fail("BUY must not be sent")
        strategy.log = SimpleNamespace(error=lambda *_args, **_kwargs: None, info=lambda *_args, **_kwargs: None)
        strategy.maybe_open_new_week(MONDAY, cash_open, None, None)
        self.assertEqual("SKIP_ARITHMETIC", recorded[0][0])

    def test_loop_records_fenced_approval_before_baseline_buy(self):
        strategy = self.strategy()
        strategy.entry_rule_controls = {key: False for key in strategy.entry_rule_controls}
        strategy.state = MODULE.StrategyState()
        strategy.last_entry_rule_error_monotonic = 0.0
        strategy.cfg.monitor_error_log_interval_seconds = 30.0
        strategy.refresh_entry_rule_context = lambda _day: self.backend([0.0, 0.0]) | {"weekState": None}
        strategy.is_new_week_entry = lambda _day: True
        cash_open = datetime.combine(MONDAY, time(15, 30), WARSAW)
        buy_action = cash_open.replace(second=0, microsecond=0)
        buy_action = buy_action.replace(second=0) - timedelta(seconds=3)
        strategy.session_times = lambda _day: SimpleNamespace(buy_action=buy_action, cash_open=cash_open)
        strategy.previous_trading_date = lambda _day: date(2026, 8, 7)
        strategy.refresh_previous_full_week_change = lambda _day: None
        strategy.entry_rule_market_context = lambda _day: self.fail("cash-open market inputs must not be read")
        recorded = []
        sent = []
        strategy.record_entry_rule_week_state = lambda _day, status, inputs: recorded.append((status, inputs)) or {}
        strategy.remember_entry_rule_decision = lambda *_args: None
        strategy.send_buy = lambda _day, scheduled_at=None: sent.append(scheduled_at) or True
        strategy.log = SimpleNamespace(error=lambda *_args, **_kwargs: None, info=lambda *_args, **_kwargs: None)
        strategy.maybe_open_new_week(MONDAY, buy_action, None, None)
        self.assertEqual("ENTRY_APPROVED", recorded[0][0])
        self.assertFalse(recorded[0][1]["cashOpenRequired"])
        self.assertEqual([buy_action], sent)


if __name__ == "__main__":
    unittest.main()
