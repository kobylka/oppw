from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    mt5.ORDER_TYPE_BUY = 0
    mt5.POSITION_TYPE_BUY = 0
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous_v50_1.py"
    spec = importlib.util.spec_from_file_location("oppw_v50_1_signal_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()
WARSAW = ZoneInfo("Europe/Warsaw")
OPEN_DAY = date(2026, 7, 20)
CASH_OPEN = datetime(2026, 7, 20, 15, 30, tzinfo=WARSAW)


class DeferredSignalOpenTests(unittest.TestCase):
    def strategy(self):
        strategy = object.__new__(MODULE.OPPWContinuousStrategy)
        strategy.tz = WARSAW
        strategy.state = MODULE.StrategyState(
            open_date=OPEN_DAY.isoformat(),
            entry_price=29000.0,
            entry_signal_daily_open=0.0,
            entry_signal_open_pending=True,
        )
        strategy.cfg = SimpleNamespace(
            break_even_ratio=0.996,
            signal_symbol="US100",
            state_file=Path(tempfile.gettempdir()) / "oppw-v50-1-signal-test-state.json",
        )
        strategy.session_times = lambda _day: SimpleNamespace(
            cash_open=CASH_OPEN,
            weekly_close=datetime(2026, 7, 20, 21, 59, 57, tzinfo=WARSAW),
        )
        strategy.last_signal_open_pending_log_monotonic = 0.0
        strategy.log = SimpleNamespace(
            info=lambda *_args, **_kwargs: None,
            warning=lambda *_args, **_kwargs: None,
        )
        strategy.emit_status = lambda *_args, **_kwargs: None
        return strategy

    def test_break_even_never_uses_early_fill_as_signal_open(self):
        strategy = self.strategy()
        position = SimpleNamespace(price_open=29123.0, time=0)
        payload = strategy.break_even_check_payload(
            position,
            datetime(2026, 7, 20, 9, 46, tzinfo=WARSAW),
        )
        self.assertEqual(payload["status"], "WAITING_FOR_SIGNAL_OPEN")
        self.assertEqual(payload["signalReference"], 0.0)
        self.assertEqual(payload["threshold"], 0.0)
        self.assertEqual(payload["nextCheckAt"], CASH_OPEN.isoformat())

    def test_cash_open_capture_is_deferred_then_committed(self):
        strategy = self.strategy()
        position = SimpleNamespace(price_open=29123.0)
        calls: list[date] = []
        strategy.signal_cash_open = lambda _symbol, day: calls.append(day) or 29463.15

        self.assertFalse(
            strategy.capture_entry_signal_open(
                position,
                datetime(2026, 7, 20, 9, 46, tzinfo=WARSAW),
            )
        )
        self.assertEqual(calls, [])
        self.assertTrue(strategy.state.entry_signal_open_pending)

        self.assertTrue(strategy.capture_entry_signal_open(position, CASH_OPEN))
        self.assertEqual(calls, [OPEN_DAY])
        self.assertFalse(strategy.state.entry_signal_open_pending)
        self.assertAlmostEqual(strategy.state.entry_signal_daily_open, 29463.15)

    def test_nonfinal_close_waits_for_real_signal_reference(self):
        strategy = self.strategy()
        position = SimpleNamespace(price_open=29123.0)
        strategy.final_trading_day = lambda _day: date(2026, 7, 24)
        strategy.live_signal_price = lambda: self.fail("must not read a CH price without its reference")
        strategy.close_position_market = lambda *_args: self.fail("must not close a non-final day without its signal reference")
        now = datetime(2026, 7, 20, 22, 0, tzinfo=WARSAW)
        self.assertFalse(strategy.maybe_execute_close_action(position, now))
        self.assertEqual(strategy.state.last_close_action_date, "")

    def test_final_weekly_to_remains_unconditional_when_signal_is_missing(self):
        strategy = self.strategy()
        position = SimpleNamespace(price_open=29123.0)
        strategy.final_trading_day = lambda day: day
        reasons: list[str] = []
        strategy.close_position_market = lambda _position, reason, _now: reasons.append(reason) or True
        now = datetime(2026, 7, 20, 22, 0, tzinfo=WARSAW)
        self.assertTrue(strategy.maybe_execute_close_action(position, now))
        self.assertEqual(reasons, ["TO"])
        self.assertEqual(strategy.state.last_close_action_date, OPEN_DAY.isoformat())


if __name__ == "__main__":
    unittest.main()
