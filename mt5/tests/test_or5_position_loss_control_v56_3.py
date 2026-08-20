from __future__ import annotations

import importlib.util
import sys
import types
import unittest
import time as time_module
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
    mt5.TIMEFRAME_M1 = 1
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
    spec = importlib.util.spec_from_file_location("oppw_v56_3_or5_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()
WARSAW = ZoneInfo("Europe/Warsaw")
MONDAY = date(2026, 8, 17)


class Or5PositionLossControlTests(unittest.TestCase):
    def strategy(self):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.tz = WARSAW
        strategy.cfg = SimpleNamespace(premarket_start=time(10, 0), state_file=Path("unused-state.json"))
        strategy.position_rule_controls = {"OR5": True}
        strategy.position_rule_controls_revision = 7
        strategy.session_times = lambda day: SimpleNamespace(
            cash_open=datetime.combine(day, time(15, 30), WARSAW),
            close_bar_open=datetime.combine(day, time(22, 0), WARSAW),
        )
        strategy.position_open_datetime = lambda _position: datetime(2026, 8, 14, 15, 30, tzinfo=WARSAW)
        return strategy

    @staticmethod
    def bar(at: datetime, *, open_price=100.0, high=100.2, low=99.8, close=100.0):
        return MODULE.M1Bar(int(at.timestamp()), at, open_price, high, low, close)

    def install_complete_windows(self, strategy, *, signal_close=99.5, signal_low=98.4):
        opening_start = datetime(2026, 8, 17, 15, 30, tzinfo=WARSAW)
        signal_at = datetime(2026, 8, 17, 16, 29, tzinfo=WARSAW)
        opening = [
            self.bar(opening_start + timedelta(minutes=index), low=99.5, close=100.0)
            for index in range(5)
        ]
        slow = [
            self.bar(opening_start + timedelta(minutes=index), low=99.5, close=100.0)
            for index in range(59)
        ] + [self.bar(signal_at, low=signal_low, close=signal_close)]
        strategy.m1_bars_inclusive = lambda _symbol, start, end: opening if end - start == timedelta(minutes=4) else slow
        return self.bar(signal_at, low=signal_low, close=signal_close)

    def test_one_qualifying_completed_close_matches_or5(self):
        strategy = self.strategy()
        signal = self.install_complete_windows(strategy)
        position = SimpleNamespace(symbol="US100", price_open=100.0, identifier=91, ticket=92)

        result = strategy.or5_rule_status(position, signal)

        self.assertEqual("MATCHED", result["rules"][0]["status"])
        self.assertTrue(all(condition["met"] for condition in result["rules"][0]["conditions"]))
        self.assertEqual(1, result["inputs"]["persistence"])
        self.assertEqual("2026-08-17T16:30:00+02:00", result["inputs"]["signalBarClosedAt"])
        self.assertEqual("ACCOUNT_MT5_M1", result["inputs"]["priceSource"])

    def test_close_above_opening_range_low_does_not_match(self):
        strategy = self.strategy()
        signal = self.install_complete_windows(strategy, signal_close=99.51)
        position = SimpleNamespace(symbol="US100", price_open=100.0, identifier=91, ticket=92)

        result = strategy.or5_rule_status(position, signal)

        self.assertEqual("NOT_MATCHED", result["rules"][0]["status"])
        condition = next(item for item in result["rules"][0]["conditions"] if item["key"] == "OPENING_RANGE_BREAK")
        self.assertFalse(condition["met"])

    def test_missing_any_minute_fails_closed_and_retries(self):
        strategy = self.strategy()
        signal = self.install_complete_windows(strategy)
        complete = strategy.m1_bars_inclusive
        strategy.m1_bars_inclusive = lambda symbol, start, end: complete(symbol, start, end)[:-1]
        position = SimpleNamespace(symbol="US100", price_open=100.0, identifier=91, ticket=92)

        result = strategy.or5_rule_status(position, signal)

        self.assertEqual("WAITING", result["rules"][0]["status"])
        self.assertIn("exact five-minute opening range", result["error"])

    def test_entry_day_does_not_borrow_premarket_minutes(self):
        strategy = self.strategy()
        strategy.position_open_datetime = lambda _position: datetime(2026, 8, 17, 15, 29, 57, tzinfo=WARSAW)
        signal_at = datetime(2026, 8, 17, 16, 0, tzinfo=WARSAW)
        position = SimpleNamespace(symbol="US100", price_open=100.0, identifier=91, ticket=92)

        result = strategy.or5_rule_status(position, self.bar(signal_at, low=98.0, close=98.5))

        self.assertEqual("WAITING", result["rules"][0]["status"])
        self.assertIn("complete eligible 60-minute", result["error"])

    def test_immutable_authorization_is_restored_even_after_rule_is_disabled(self):
        strategy = self.strategy()
        strategy.role = "PUBLISHER"
        strategy.log = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        strategy.position_rule_observed_after_utc = 0
        strategy.last_position_rule_context_success_monotonic = 0.0
        strategy.state = MODULE.StrategyState(
            active_position_identifier=91,
            entry_price=100.0,
        )
        payload = {
            "positionRevision": 8,
            "positionRules": [{"key": "OR5", "enabled": False}],
            "positionTrigger": {
                "requestId": "a" * 32,
                "positionIdentifier": 91,
                "recordedAt": "2026-08-17T16:30:01+02:00",
                "inputs": {"controlsRevision": 7, "signalClose": 98.5},
            },
        }

        strategy.apply_position_rule_context(payload)

        self.assertFalse(strategy.position_rule_controls["OR5"])
        self.assertEqual("a" * 32, strategy.state.or5_authorized_request_id)
        self.assertEqual("OR5", strategy.state.exit_latched_reason)

    def test_candle_completed_before_enablement_boundary_is_not_retroactive(self):
        strategy = self.strategy()
        strategy.account = "DEMO"
        strategy.last_position_rule_error_monotonic = 0.0
        strategy.last_position_rule_context_success_monotonic = time_module.monotonic()
        strategy.cfg.monitor_publish_interval_seconds = 5.0
        strategy.cfg.monitor_error_log_interval_seconds = 30.0
        strategy.log = SimpleNamespace(error=lambda *_args, **_kwargs: None)
        strategy.state = SimpleNamespace(
            or5_authorized_request_id="",
            or5_authorized_position_identifier=0,
            or5_last_evaluated_bar_utc=0,
            save=lambda _path: None,
        )
        strategy.refresh_entry_rule_context = lambda _day: {}
        signal_at = datetime(2026, 8, 17, 16, 29, tzinfo=WARSAW)
        raw_signal = int(strategy.local_to_mt5_bar_query_time(signal_at).timestamp())
        strategy.previous_m1_bar = lambda *_args: MODULE.M1Bar(raw_signal, signal_at, 100.0, 100.0, 98.0, 98.5)
        boundary = datetime(2026, 8, 17, 16, 30, tzinfo=WARSAW)
        strategy.position_rule_observed_after_utc = int(strategy.local_to_mt5_bar_query_time(boundary).timestamp())
        strategy.or5_rule_status = lambda *_args: self.fail("pre-boundary candle must not be evaluated")
        position = SimpleNamespace(symbol="US100", price_open=100.0, identifier=91, ticket=92)

        acted = strategy.evaluate_or5_completed_bar(position, boundary)

        self.assertFalse(acted)
        self.assertEqual(0, strategy.state.or5_last_evaluated_bar_utc)


if __name__ == "__main__":
    unittest.main()
