from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    mt5.ORDER_TYPE_BUY = 0
    mt5.POSITION_TYPE_BUY = 0
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
    spec = importlib.util.spec_from_file_location("oppw_v49_1_tsl_market_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()
MT5 = sys.modules["MetaTrader5"]
WARSAW = ZoneInfo("Europe/Warsaw")


class TslMarketExitTests(unittest.TestCase):
    def test_bid_at_or_below_tsl_closes_at_market_before_exit_bracket(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = object.__new__(MODULE.OPPWContinuousStrategy)
            strategy.state = MODULE.StrategyState(
                active_position_identifier=777,
                active_position_ticket=123,
                entry_price=29_000.0,
                entry_leverage=10,
                exit_latched_reason="",
                immutable_hard_sl_position_identifier=777,
                immutable_hard_sl_price=27_550.0,
                immutable_hard_sl_leverage=10,
                first_protection_confirmed=True,
            )
            strategy.cfg = SimpleNamespace(
                state_file=Path(temp_dir) / "state.json",
                tsl_stop=0.004,
                tsl_ratio=0.996,
                break_even_ratio=0.996,
                base_leverage=8,
                loss_leverage=10,
                leverage_stop_points=50.0,
            )
            strategy.log = SimpleNamespace(
                warning=lambda *_args, **_kwargs: None,
                info=lambda *_args, **_kwargs: None,
            )
            strategy.immutable_hard_stop_matches = lambda _position: True
            strategy.lock_immutable_hard_stop = lambda *_args: self.fail("immutable stop must not be recalculated")
            strategy.fresh_tick_for_protection = lambda *_args: SimpleNamespace(bid=28_884.0, ask=28_885.0)
            strategy.broker_minimum_distance = lambda _info: 1.0
            strategy.arm_exit = lambda *_args: self.fail("crossed TSL must not use arm_exit")
            market_closes = []
            strategy.close_position_market = lambda _position, reason, _now: market_closes.append(reason) or True
            MT5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)
            position = SimpleNamespace(
                identifier=777,
                ticket=123,
                symbol="US100",
                price_open=29_000.0,
                volume=0.02,
                sl=27_550.0,
                tp=0.0,
            )

            result = strategy.apply_standard_protection(
                position, datetime(2026, 7, 23, 0, 0, tzinfo=WARSAW)
            )

            self.assertTrue(result)
            self.assertEqual(market_closes, ["TSL"])


if __name__ == "__main__":
    unittest.main()
