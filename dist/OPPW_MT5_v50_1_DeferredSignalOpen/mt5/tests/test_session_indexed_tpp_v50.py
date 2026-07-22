from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    mt5.ORDER_TYPE_BUY = 0
    mt5.POSITION_TYPE_BUY = 0
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous_v50.py"
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
        )
        strategy.trading_sessions_for_week = lambda _day: sessions
        strategy.session_times = lambda day: SimpleNamespace(
            cash_open=datetime(day.year, day.month, day.day, 15, 30, tzinfo=WARSAW)
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


if __name__ == "__main__":
    unittest.main()
