from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    mt5.ORDER_TYPE_BUY = 0
    mt5.POSITION_TYPE_BUY = 0
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
    spec = importlib.util.spec_from_file_location("oppw_v50_tpp_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()
WARSAW = ZoneInfo("Europe/Warsaw")
TPPS = (0.007, 0.020, 0.050, 0.050, 0.050)


class SessionIndexedTppTests(unittest.TestCase):
    def strategy(self, sessions: list[date], opened: date):
        strategy = object.__new__(MODULE.OPPWContinuousStrategy)
        strategy.tz = WARSAW
        strategy.state = MODULE.StrategyState(open_date=opened.isoformat(), break_even=False)
        strategy.cfg = SimpleNamespace(
            tpps=TPPS,
            premarket_start=time(0, 0),
            break_even_ratio=0.996,
            trade_symbol="US100",
            signal_symbol="US100",
            entry_action_lead_seconds=3.0,
            non_entry_action_lead_seconds=3.0,
            magic=240024,
        )
        strategy.trading_sessions_for_week = lambda _day: sessions
        strategy.session_times = lambda day: SimpleNamespace(
            buy_action=datetime(day.year, day.month, day.day, 9, 45, tzinfo=WARSAW),
            open_action=datetime(day.year, day.month, day.day, 15, 29, 57, tzinfo=WARSAW),
            cash_open=datetime(day.year, day.month, day.day, 15, 30, tzinfo=WARSAW),
            weekly_close=datetime(day.year, day.month, day.day, 21, 59, 57, tzinfo=WARSAW),
            close_bar_open=datetime(day.year, day.month, day.day, 22, 0, tzinfo=WARSAW),
            close_processing=datetime(day.year, day.month, day.day, 22, 1, tzinfo=WARSAW),
        )
        strategy.log = SimpleNamespace(info=lambda *_args, **_kwargs: None)
        return strategy

    def test_regular_week_uses_calendar_equivalent_tpps(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        self.assertEqual([strategy.tpp_for_day(day) for day in sessions], list(TPPS))

    def test_tuesday_first_week_shifts_every_tpp_one_session(self):
        sessions = [date(2026, 7, day) for day in range(21, 25)]
        strategy = self.strategy(sessions, sessions[0])
        self.assertEqual(
            [strategy.tpp_for_day(day) for day in sessions],
            [0.007, 0.020, 0.050, 0.050],
        )

    def test_normal_tuesday_pre_h_ramps_from_point_seven_to_two_percent(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        second_day = sessions[1]
        midnight = datetime.combine(second_day, time(0, 0), WARSAW)
        cash_open = datetime.combine(second_day, time(15, 30), WARSAW)
        self.assertAlmostEqual(strategy.premarket_high_tpp(None, midnight), 0.007)
        self.assertAlmostEqual(strategy.premarket_high_tpp(None, cash_open), 0.020)

    def test_tuesday_first_week_pre_h_ramps_on_wednesday(self):
        sessions = [date(2026, 7, day) for day in range(21, 25)]
        strategy = self.strategy(sessions, sessions[0])
        wednesday = sessions[1]
        midnight = datetime.combine(wednesday, time(0, 0), WARSAW)
        cash_open = datetime.combine(wednesday, time(15, 30), WARSAW)
        self.assertAlmostEqual(strategy.premarket_high_tpp(None, midnight), 0.007)
        self.assertAlmostEqual(strategy.premarket_high_tpp(None, cash_open), 0.020)

    def test_ordinary_wednesday_has_no_pre_h_ramp(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        wednesday = sessions[2]
        now = datetime.combine(wednesday, time(8, 0), WARSAW)
        self.assertIsNone(strategy.premarket_high_tpp(None, now))

    def test_crossed_pre_h_uses_market_close(self):
        sessions = [date(2026, 7, day) for day in range(21, 25)]
        strategy = self.strategy(sessions, sessions[0])
        closes: list[str] = []
        strategy.close_position_market = lambda _position, reason, _now: closes.append(reason) or True
        wednesday = sessions[1]
        bar_time = datetime.combine(wednesday, time(8, 0), WARSAW)
        position = SimpleNamespace(price_open=100.0)
        bar = MODULE.M1Bar(1, bar_time, 101.40, 101.40, 101.40, 101.40)
        strategy.evaluate_premarket_open(position, bar, bar_time)
        self.assertEqual(closes, ["PRE H"])

    def test_mobile_condition_contains_current_potential_tp_percent(self):
        sessions = [date(2026, 7, day) for day in range(21, 25)]
        strategy = self.strategy(sessions, sessions[0])
        strategy.weekday_sl_target = lambda _position, _now: (95.0, "SL")
        MODULE.mt5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)
        wednesday = sessions[1]
        now = datetime.combine(wednesday, time(8, 0), WARSAW)
        position = SimpleNamespace(symbol="US100", price_open=100.0, sl=95.0, tp=0.0)
        conditions = strategy.monitor_all_conditions(position, now, 100.0, 100.0)
        pre_h = next(condition for condition in conditions if condition["name"] == "PRE H")
        self.assertAlmostEqual(pre_h["potentialTpPercent"], 1.370967741935484)

    def test_scheduled_break_even_check_participates_in_closest_condition(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        strategy.cfg.signal_symbol = "QQQ"
        strategy.weekday_sl_target = lambda _position, _now: (95.0, "SL")
        MODULE.mt5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)
        now = datetime.combine(sessions[2], time(16, 0), WARSAW)
        position = SimpleNamespace(symbol="US100", price_open=100.0, sl=95.0, tp=0.0)

        conditions = strategy.monitor_all_conditions(
            position,
            now,
            100.0,
            99.0,
            {"status": "SCHEDULED", "threshold": 98.0},
        )

        break_even = next(condition for condition in conditions if condition["name"] == "BE CHECK")
        self.assertEqual(break_even["source"], "QQQ")
        self.assertAlmostEqual(break_even["targetPrice"], 98.0)
        self.assertAlmostEqual(break_even["currentPrice"], 99.0)
        self.assertEqual(strategy.monitor_closest_condition(conditions)["name"], "BE CHECK")

    def test_oh_is_never_eligible_on_first_actual_session(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        self.assertFalse(strategy.oh_check_eligible(sessions[0]))
        self.assertTrue(strategy.oh_check_eligible(sessions[1]))
        self.assertFalse(strategy.break_even_check_eligible(date(2026, 7, 19), sessions[0]))
        self.assertTrue(strategy.break_even_check_eligible(sessions[0], sessions[1]))

    def test_first_session_mobile_status_has_no_oh_condition_or_next_action(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        strategy.weekday_sl_target = lambda _position, _now: (95.0, "SL")
        strategy.final_trading_day = lambda _day: sessions[-1]
        MODULE.mt5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)
        now = datetime.combine(sessions[0], time(12, 0), WARSAW)
        position = SimpleNamespace(symbol="US100", price_open=100.0, sl=0.0, tp=0.0)

        conditions = strategy.monitor_all_conditions(position, now, 100.0, 100.0)
        next_action, _ = strategy.monitor_next_action(position, now)

        self.assertNotIn("OH", {condition["name"] for condition in conditions})
        self.assertEqual(next_action, "CH")

    def test_first_session_open_action_is_skipped_without_reading_a_tick(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        strategy.state.exit_latched_reason = ""
        strategy.state.last_open_action_date = ""
        strategy.state.save = lambda _path: None
        strategy.cfg.state_file = Path("unused.json")
        strategy.require_fresh_tick = lambda _symbol: self.fail("first-session OH must not read a tick")
        position = SimpleNamespace(symbol="US100", price_open=100.0)
        now = datetime.combine(sessions[0], time(15, 29, 57), WARSAW)

        self.assertFalse(strategy.maybe_execute_open_action(position, now))
        self.assertEqual(strategy.state.last_open_action_date, sessions[0].isoformat())

    def test_week_open_reference_uses_exact_first_session_cash_open(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        calls = []
        strategy.m1_bar_at = lambda symbol, day, at: calls.append((symbol, day, at)) or SimpleNamespace(open=29_463.15)
        before = datetime.combine(sessions[0], time(15, 0), WARSAW)
        after = datetime.combine(sessions[0], time(16, 0), WARSAW)

        _, pending_price = strategy.week_open_reference(sessions[0], before)
        cash_open_at, open_price = strategy.week_open_reference(sessions[0], after)
        _, cached_price = strategy.week_open_reference(sessions[1], datetime.combine(sessions[1], time(16, 0), WARSAW))

        self.assertEqual(pending_price, 0.0)
        self.assertEqual(cash_open_at, "2026-07-20T15:30:00+02:00")
        self.assertAlmostEqual(open_price, 29_463.15)
        self.assertAlmostEqual(cached_price, 29_463.15)
        self.assertEqual(len(calls), 1)

    def test_daily_close_processing_uses_completed_session_close_authority(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        strategy.cfg.signal_symbol = "QQQ"
        strategy.cfg.state_file = Path("unused-state.json")
        strategy.state.last_close_processed_date = ""
        strategy.state.prev_open = 100.0
        strategy.state.save = lambda _path: None
        strategy.final_trading_day = lambda _day: sessions[-1]
        calls = []
        strategy.completed_session_close_bar = lambda symbol, day: (
            calls.append((symbol, day))
            or SimpleNamespace(close=110.0 if symbol == "US100" else 90.0)
        )
        messages = []
        strategy.log = SimpleNamespace(info=lambda message, *args: messages.append(message % args))

        strategy.process_completed_close(
            sessions[-1], datetime.combine(sessions[-1], time(22, 1), WARSAW), None,
        )

        self.assertEqual(calls, [("US100", sessions[-1]), ("QQQ", sessions[-1])])
        self.assertAlmostEqual(0.10, strategy.state.prev_full_week_change)
        self.assertEqual(sessions[-1].isoformat(), strategy.state.last_close_processed_date)
        self.assertTrue(any("DAILY_CLOSE_PROCESSED" in message for message in messages))

    def test_break_even_reconstruction_uses_completed_signal_close(self):
        sessions = [date(2026, 7, day) for day in range(20, 25)]
        strategy = self.strategy(sessions, sessions[0])
        strategy.cfg.signal_symbol = "QQQ"
        strategy.cfg.break_even_ratio = 0.996
        strategy.calendar = SimpleNamespace(
            sessions_in_range=lambda *_args: [datetime.combine(sessions[1], time(0, 0), WARSAW)],
        )
        strategy.break_even_check_eligible = lambda *_args: True
        calls = []
        strategy.completed_session_close_bar = lambda symbol, day: (
            calls.append((symbol, day)) or SimpleNamespace(close=99.0)
        )

        reconstructed = strategy.reconstruct_break_even(
            sessions[0], 100.0, datetime.combine(sessions[2], time(22, 2), WARSAW),
        )

        self.assertTrue(reconstructed)
        self.assertEqual(calls, [("QQQ", sessions[1])])

    def test_current_w1_bar_supplies_week_ohlc_before_cash_open(self):
        sessions = [date(2026, 7, day) for day in range(27, 32)]
        strategy = self.strategy(sessions, sessions[0])
        strategy.is_trading_session_day = lambda day: day in sessions
        strategy.previous_trading_date = lambda _day: date(2026, 7, 24)
        timestamp = int(datetime(2026, 7, 27, 0, 0, tzinfo=UTC).timestamp())
        MODULE.mt5.TIMEFRAME_W1 = 10_080
        MODULE.mt5.copy_rates_from_pos = lambda symbol, timeframe, start, count: [
            {"time": timestamp, "open": 28_600.0, "high": 28_750.0, "low": 28_550.0, "close": 28_700.0},
        ]

        bar = strategy.current_w1_bar("US100", datetime(2026, 7, 27, 12, 0, tzinfo=WARSAW))
        session = strategy.market_session_payload(datetime(2026, 7, 27, 12, 0, tzinfo=WARSAW), bar)

        self.assertIsNotNone(bar)
        self.assertEqual((bar.open, bar.high, bar.low, bar.close), (28_600.0, 28_750.0, 28_550.0, 28_700.0))
        self.assertEqual(session["weekMarketOpenPrice"], 28_600.0)
        self.assertEqual(session["weekMarketOpenSource"], "MT5_M1_WINDOW")
        self.assertIsNone(session["weekOpenPrice"])

    def test_current_week_window_starts_at_cash_open_without_a_manual_position(self):
        sessions = [date(2026, 7, day) for day in range(27, 32)]
        strategy = self.strategy(sessions, sessions[0])
        strategy.local_to_mt5_bar_query_time = lambda value: value
        strategy.mt5_bar_timestamp_to_local = lambda value: datetime.fromtimestamp(value, UTC).astimezone(WARSAW)
        before = datetime(2026, 7, 27, 15, 29, tzinfo=WARSAW)
        opening = datetime(2026, 7, 27, 15, 30, tzinfo=WARSAW)
        later = datetime(2026, 7, 27, 15, 31, tzinfo=WARSAW)
        MODULE.mt5.TIMEFRAME_M1 = 1
        MODULE.mt5.copy_rates_range = lambda *_args: [
            {"time": int(before.timestamp()), "open": 90.0, "high": 95.0, "low": 80.0, "close": 91.0},
            {"time": int(opening.timestamp()), "open": 100.0, "high": 106.0, "low": 99.0, "close": 104.0},
            {"time": int(later.timestamp()), "open": 104.0, "high": 108.0, "low": 103.0, "close": 107.0},
        ]

        bar = strategy.current_week_market_bar(
            "US100", datetime(2026, 7, 27, 15, 31, 30, tzinfo=WARSAW)
        )

        self.assertIsNotNone(bar)
        self.assertEqual(bar.local_datetime, opening)
        self.assertEqual((bar.open, bar.high, bar.low, bar.close), (100.0, 108.0, 99.0, 107.0))

    def test_manual_preopen_position_defines_week_window_and_fill_is_included(self):
        sessions = [date(2026, 7, day) for day in range(27, 32)]
        strategy = self.strategy(sessions, sessions[0])
        strategy.local_to_mt5_bar_query_time = lambda value: value
        strategy.mt5_bar_timestamp_to_local = lambda value: datetime.fromtimestamp(value, UTC).astimezone(WARSAW)
        strategy.mt5_timestamp_to_local = strategy.mt5_bar_timestamp_to_local
        opened = datetime(2026, 7, 27, 14, 45, tzinfo=WARSAW)
        later = datetime(2026, 7, 27, 14, 46, tzinfo=WARSAW)
        position = SimpleNamespace(magic=0, time=int(opened.timestamp()), time_msc=0, price_open=97.0)
        MODULE.mt5.TIMEFRAME_M1 = 1
        MODULE.mt5.copy_rates_range = lambda *_args: [
            {"time": int(opened.timestamp()), "open": 100.0, "high": 105.0, "low": 99.0, "close": 101.0},
            {"time": int(later.timestamp()), "open": 101.0, "high": 103.0, "low": 98.0, "close": 102.0},
        ]

        bar = strategy.current_week_market_bar(
            "US100", datetime(2026, 7, 27, 14, 46, 30, tzinfo=WARSAW), position
        )

        self.assertIsNotNone(bar)
        self.assertEqual(bar.local_datetime, opened)
        self.assertEqual((bar.open, bar.high, bar.low, bar.close), (97.0, 105.0, 97.0, 102.0))

    def test_stale_state_does_not_arm_manual_position_or_schedule_first_day_checks(self):
        sessions = [date(2026, 7, day) for day in range(27, 32)]
        strategy = self.strategy(sessions, date(2026, 7, 20))
        strategy.state.active_position_identifier = 999
        strategy.state.entry_price = 30_000.0
        strategy.state.break_even = True
        strategy.state.last_open_action_date = sessions[0].isoformat()
        strategy.state.last_close_action_date = sessions[1].isoformat()
        opened_timestamp = int(datetime(2026, 7, 27, 0, 0, tzinfo=UTC).timestamp())
        position = SimpleNamespace(
            identifier=777, ticket=123, symbol="US100", price_open=28_600.0,
            time=opened_timestamp, sl=0.0, tp=0.0,
        )
        now = datetime(2026, 7, 27, 12, 0, tzinfo=WARSAW)
        strategy.final_trading_day = lambda _day: sessions[-1]

        break_even = strategy.break_even_check_payload(position, now)
        next_action, _ = strategy.monitor_next_action(position, now)

        self.assertEqual(break_even["status"], "SCHEDULED_SIGNAL_PENDING")
        self.assertEqual(break_even["nextCheckAt"], "2026-07-28T21:59:57+02:00")
        self.assertEqual(next_action, "CH")


if __name__ == "__main__":
    unittest.main()
