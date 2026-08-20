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
    mt5.TIMEFRAME_M1 = 1
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
            trade_symbol="US100",
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

    def test_publisher_control_refresh_never_persists_executor_state(self):
        strategy = self.strategy()
        strategy.role = "PUBLISHER"
        strategy.state = SimpleNamespace(
            entry_rule_controls_revision=3,
            entry_rule_controls=dict(strategy.entry_rule_controls),
            save=lambda _path: self.fail("publisher must not persist executor state"),
        )
        strategy.cfg.state_file = Path("unused-state.json")
        strategy.log = SimpleNamespace(info=lambda *_args: None)
        payload = {
            "revision": 4,
            "rules": [
                {"key": key, "enabled": key != "PREMARKET_LOW"}
                for key in strategy.entry_rule_controls
            ],
        }

        strategy.apply_entry_rule_context(payload)

        self.assertEqual(4, strategy.entry_rule_controls_revision)
        self.assertFalse(strategy.entry_rule_controls["PREMARKET_LOW"])
        self.assertEqual(3, strategy.state.entry_rule_controls_revision)

    def test_pre_cash_open_market_preview_includes_current_price(self):
        strategy = self.strategy()
        strategy.tz = WARSAW
        strategy.cfg.trade_symbol = "US100"
        strategy.cfg.premarket_start = time(0, 0)
        cash_open = datetime(2026, 8, 10, 15, 30, tzinfo=WARSAW)
        strategy.session_times = lambda _day: SimpleNamespace(cash_open=cash_open)
        strategy.m1_bar_at = lambda *_args: SimpleNamespace(open=90.0)
        strategy.calendar = SimpleNamespace(sessions_in_range=lambda *_args: [])
        strategy.local_to_mt5_bar_query_time = lambda value: value
        strategy.mt5_bar_timestamp_to_local = lambda value: datetime.fromtimestamp(value, WARSAW)
        had_copy_rates_range = hasattr(MODULE.mt5, "copy_rates_range")
        old_copy_rates_range = getattr(MODULE.mt5, "copy_rates_range", None)
        MODULE.mt5.copy_rates_range = lambda *_args: [{
            "time": int(datetime(2026, 8, 10, 15, 28, tzinfo=WARSAW).timestamp()),
            "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.4,
        }]
        self.addCleanup(
            setattr if had_copy_rates_range else delattr,
            MODULE.mt5, "copy_rates_range", *([old_copy_rates_range] if had_copy_rates_range else []),
        )

        market = strategy.entry_rule_market_context(
            MONDAY, preview_price=101.0,
            preview_at=datetime(2026, 8, 10, 15, 29, tzinfo=WARSAW),
        )

        self.assertEqual("CURRENT_BUY_PRICE_PREVIEW", market["cashOpenSource"])
        self.assertEqual(101.0, market["cashOpen"])
        self.assertEqual(101.0, market["premarketHigh"])
        self.assertEqual(101.0, market["premarketClose"])

    def test_completed_session_close_uses_2159_bar_for_2200_bossa_close(self):
        strategy = self.strategy()
        strategy.tz = WARSAW
        strategy.cfg.monitor_error_log_interval_seconds = 30.0
        friday = date(2026, 8, 14)
        boundary = datetime(2026, 8, 14, 22, 0, tzinfo=WARSAW)
        strategy.session_times = lambda _day: SimpleNamespace(close_bar_open=boundary)
        strategy.local_to_mt5_bar_query_time = lambda value: value
        strategy.mt5_bar_timestamp_to_local = lambda value: datetime.fromtimestamp(value, WARSAW)
        strategy.log = SimpleNamespace(warning=lambda *_args: self.fail("valid close must not warn"))
        calls = []
        MODULE.mt5.copy_rates_range = lambda *_args: calls.append(True) or [
            {
                "time": int(datetime(2026, 8, 14, 21, 59, tzinfo=WARSAW).timestamp()),
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
            },
            {
                "time": int(datetime(2026, 8, 14, 22, 0, tzinfo=WARSAW).timestamp()),
                "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5,
            },
        ]

        first = strategy.completed_session_close_bar("US100", friday)
        second = strategy.completed_session_close_bar("US100", friday)

        self.assertIsNotNone(first)
        self.assertEqual(datetime(2026, 8, 14, 21, 59, tzinfo=WARSAW), first.local_datetime)
        self.assertEqual(100.5, first.close)
        self.assertIs(first, second)
        self.assertEqual(1, len(calls), "successful historical closes must be cached")

    def test_completed_session_close_uses_calendar_boundary_in_winter_and_early_close(self):
        for session_day, boundary_time in (
            (date(2026, 1, 9), time(22, 0)),
            (date(2026, 11, 27), time(19, 0)),
        ):
            with self.subTest(session_day=session_day, boundary_time=boundary_time):
                strategy = self.strategy()
                strategy.tz = WARSAW
                strategy.cfg.monitor_error_log_interval_seconds = 30.0
                boundary = datetime.combine(session_day, boundary_time, WARSAW)
                selected_at = boundary - timedelta(minutes=1)
                strategy.session_times = lambda _day, value=boundary: SimpleNamespace(close_bar_open=value)
                strategy.local_to_mt5_bar_query_time = lambda value: value
                strategy.mt5_bar_timestamp_to_local = lambda value: datetime.fromtimestamp(value, WARSAW)
                strategy.log = SimpleNamespace(warning=lambda *_args: self.fail("valid close must not warn"))
                MODULE.mt5.copy_rates_range = lambda *_args, selected=selected_at, excluded=boundary: [
                    {
                        "time": int(selected.timestamp()),
                        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                    },
                    {
                        "time": int(excluded.timestamp()),
                        "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5,
                    },
                ]

                bar = strategy.completed_session_close_bar("US100", session_day)

                self.assertIsNotNone(bar)
                self.assertEqual(selected_at, bar.local_datetime)
                self.assertEqual(100.5, bar.close)

    def test_completed_session_close_failure_retries_but_throttles_diagnostics(self):
        strategy = self.strategy()
        strategy.tz = WARSAW
        strategy.cfg.monitor_error_log_interval_seconds = 1_000_000.0
        friday = date(2026, 8, 14)
        boundary = datetime(2026, 8, 14, 22, 0, tzinfo=WARSAW)
        strategy.session_times = lambda _day: SimpleNamespace(close_bar_open=boundary)
        strategy.local_to_mt5_bar_query_time = lambda value: value
        strategy.mt5_bar_timestamp_to_local = lambda value: datetime.fromtimestamp(value, WARSAW)
        warnings = []
        strategy.log = SimpleNamespace(warning=lambda message, *args: warnings.append(message % args))
        calls = []
        MODULE.mt5.copy_rates_range = lambda *_args: calls.append(True) or []
        MODULE.mt5.last_error = lambda: (4401, "history unavailable")

        self.assertIsNone(strategy.completed_session_close_bar("US100", friday))
        self.assertIsNone(strategy.completed_session_close_bar("US100", friday))

        self.assertEqual(2, len(calls), "missing history must remain retryable")
        self.assertEqual(1, len(warnings), "retries must not create a warning storm")
        self.assertIn("boundary=2026-08-14T22:00:00+02:00", warnings[0])
        self.assertIn("history unavailable", warnings[0])

    def test_entry_market_context_audits_selected_historical_candle_times(self):
        strategy = self.strategy()
        strategy.tz = WARSAW
        strategy.cfg.premarket_start = time(0, 0)
        cash_open = datetime(2026, 8, 10, 15, 30, tzinfo=WARSAW)
        strategy.session_times = lambda day: SimpleNamespace(
            cash_open=cash_open if day == MONDAY else datetime.combine(day, time(15, 30), WARSAW),
        )
        session_days = [
            date(2026, 7, 10) + timedelta(days=value)
            for value in range(29)
            if (date(2026, 7, 10) + timedelta(days=value)).weekday() < 5
        ]
        strategy.calendar = SimpleNamespace(
            sessions_in_range=lambda *_args: [datetime.combine(day, time(0, 0), WARSAW) for day in session_days],
        )
        strategy.m1_bar_at = lambda *_args: None
        strategy.completed_session_close_bar = lambda _symbol, day: MODULE.M1Bar(
            int(datetime.combine(day, time(21, 59), WARSAW).timestamp()),
            datetime.combine(day, time(21, 59), WARSAW),
            95.0, 101.0, 94.0, 100.0 if day == session_days[-1] else 95.0,
        )
        strategy.local_to_mt5_bar_query_time = lambda value: value
        strategy.mt5_bar_timestamp_to_local = lambda value: datetime.fromtimestamp(value, WARSAW)
        MODULE.mt5.copy_rates_range = lambda *_args: [{
            "time": int(datetime(2026, 8, 10, 15, 28, tzinfo=WARSAW).timestamp()),
            "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.4,
        }]

        market = strategy.entry_rule_market_context(
            MONDAY, preview_price=101.0,
            preview_at=datetime(2026, 8, 10, 15, 29, 57, tzinfo=WARSAW),
            preview_source="ENTRY_ACTION_BUY_PRICE",
        )

        self.assertEqual(100.0, market["previousCashClose"])
        self.assertEqual(95.0, market["momentumBaseClose"])
        self.assertEqual("2026-08-07T21:59:00+02:00", market["previousCashCloseAt"])
        self.assertEqual("2026-07-10T21:59:00+02:00", market["momentumBaseCloseAt"])
        self.assertAlmostEqual(100.0 / 95.0 - 1.0, market["momentum20"])

    def test_missing_gap_inputs_are_named_for_fail_closed_diagnostics(self):
        strategy = self.strategy()
        strategy.entry_rule_controls["PREMARKET_LOW"] = False
        market = self.quiet_market() | {"previousCashClose": 0.0, "momentum20": None}

        status, inputs = strategy.loss_control_entry_decision(MONDAY, self.backend([0.0, 0.0]), market)

        self.assertEqual("WAIT_MARKET_INPUTS", status)
        self.assertEqual(["previousCashClose", "momentum20"], inputs["missingInputs"])

    def test_live_status_includes_every_rule_disabled_state_threshold_and_condition(self):
        strategy = self.strategy()
        strategy.role = "EXECUTOR"
        strategy.connected = True
        strategy.entry_rule_controls["PREMARKET_LOW"] = False
        strategy.last_entry_rule_context = None
        strategy.refresh_entry_rule_context = lambda _day: self.backend([-0.011, -0.010]) | {"weekState": None}
        strategy.entry_rule_market_context = lambda *_args, **_kwargs: self.quiet_market() | {
            "cashOpen": 101.0,
            "previousCashClose": 100.0,
            "momentum20": -0.005,
            "premarketOpen": 100.0,
            "premarketHigh": 100.8,
            "premarketLow": 100.0,
            "premarketClose": 100.12,
        }

        status = strategy.live_loss_control_status(
            datetime(2026, 8, 10, 15, 29, tzinfo=WARSAW), 101.0,
        )

        self.assertEqual(101.0, status["currentPrice"])
        self.assertEqual(
            ["ARITHMETIC_LAST_TWO", "GAP_MOMENTUM", "TUESDAY_NORMALIZATION", "PREMARKET_LOW"],
            [rule["key"] for rule in status["rules"]],
        )
        self.assertEqual("MATCHED", status["rules"][0]["status"])
        self.assertEqual(-0.02, status["rules"][0]["conditions"][0]["threshold"])
        self.assertEqual(2, len(status["rules"][1]["conditions"]))
        self.assertEqual("NOT_APPLICABLE", status["rules"][2]["status"])
        self.assertEqual("DISABLED", status["rules"][3]["status"])
        self.assertTrue(all("actual" in condition and "threshold" in condition for rule in status["rules"] for condition in rule["conditions"]))

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
        strategy.require_fresh_tick = lambda _symbol: SimpleNamespace(ask=100.0)
        strategy.entry_rule_market_context = lambda *_args, **_kwargs: self.quiet_market()
        recorded = []
        strategy.record_entry_rule_week_state = lambda _day, status, inputs: recorded.append((status, inputs)) or {}
        strategy.remember_entry_rule_decision = lambda *_args: None
        strategy.send_buy = lambda *_args, **_kwargs: self.fail("BUY must not be sent")
        strategy.log = SimpleNamespace(error=lambda *_args, **_kwargs: None, info=lambda *_args, **_kwargs: None)
        strategy.maybe_open_new_week(MONDAY, cash_open, None, None)
        self.assertEqual("SKIP_ARITHMETIC", recorded[0][0])

    def test_loop_evaluates_live_buy_price_and_sends_at_preopen_buy_action(self):
        strategy = self.strategy()
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
        strategy.require_fresh_tick = lambda _symbol: SimpleNamespace(ask=101.25)
        market_calls = []
        strategy.entry_rule_market_context = lambda day, preview_price=None, preview_at=None, preview_source="": (
            market_calls.append((day, preview_price, preview_at, preview_source))
            or self.quiet_market() | {"cashOpen": preview_price, "cashOpenSource": preview_source}
        )
        recorded = []
        sent = []
        strategy.record_entry_rule_week_state = lambda _day, status, inputs: recorded.append((status, inputs)) or {}
        strategy.remember_entry_rule_decision = lambda *_args: None
        strategy.send_buy = lambda _day, scheduled_at=None: sent.append(scheduled_at) or True
        strategy.log = SimpleNamespace(error=lambda *_args, **_kwargs: None, info=lambda *_args, **_kwargs: None)
        strategy.maybe_open_new_week(MONDAY, buy_action, None, None)
        self.assertEqual("ENTRY_APPROVED", recorded[0][0])
        self.assertFalse(recorded[0][1]["cashOpenRequired"])
        self.assertTrue(recorded[0][1]["entryPriceRequired"])
        self.assertEqual(101.25, recorded[0][1]["cashOpen"])
        self.assertEqual("ENTRY_ACTION_BUY_PRICE", recorded[0][1]["entryPriceSource"])
        self.assertEqual([(MONDAY, 101.25, buy_action, "ENTRY_ACTION_BUY_PRICE")], market_calls)
        self.assertEqual([buy_action], sent)

    def test_missed_window_records_last_named_market_inputs(self):
        strategy = self.strategy()
        strategy.state = MODULE.StrategyState()
        strategy.state.save = lambda _path: None
        strategy.cfg.state_file = Path("unused-state.json")
        strategy.exit_latched_reason = ""
        strategy.refresh_entry_rule_context = lambda _day: self.backend([0.0, 0.0]) | {"weekState": None}
        strategy.is_new_week_entry = lambda _day: True
        cash_open = datetime.combine(MONDAY, time(15, 30), WARSAW)
        buy_action = cash_open - timedelta(seconds=3)
        strategy.session_times = lambda _day: SimpleNamespace(buy_action=buy_action, cash_open=cash_open)
        strategy.last_entry_market_wait_week = "2026-W33"
        strategy.last_entry_market_wait_inputs = ["previousCashClose", "momentum20"]
        strategy.bind_execution_to_latest_decision = lambda: None
        stages = []
        strategy.execution_stage = lambda stage, **values: stages.append((stage, values))
        strategy.log = SimpleNamespace(error=lambda *_args, **_kwargs: None)

        strategy.maybe_open_new_week(
            MONDAY, buy_action + timedelta(seconds=55, microseconds=1), None, None,
        )

        self.assertEqual("MISSED_WINDOW", stages[0][0])
        self.assertEqual(
            "entry_window_elapsed_missing_previousCashClose_momentum20",
            stages[0][1]["reason"],
        )


if __name__ == "__main__":
    unittest.main()
