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
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous_v49_2.py"
    spec = importlib.util.spec_from_file_location("oppw_v49_2_tsl_deferred_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()
MT5 = sys.modules["MetaTrader5"]
WARSAW = ZoneInfo("Europe/Warsaw")


class TslDeferredInstallTests(unittest.TestCase):
    def make_strategy(self, temp_dir: str, tick):
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
        strategy.tsl_install_deferred = False
        strategy.immutable_hard_stop_matches = lambda _position: True
        strategy.lock_immutable_hard_stop = lambda *_args: self.fail("immutable stop must not be recalculated")
        strategy.fresh_tick_for_protection = lambda *_args: tick
        strategy.broker_minimum_distance = lambda _info: 10.0
        strategy.arm_exit = lambda *_args: self.fail("TSL defer/cross paths must not use arm_exit")
        market_closes = []
        modifications = []
        strategy.close_position_market = lambda _position, reason, _now: market_closes.append(reason) or True
        strategy.modify_sltp = lambda _position, sl, tp, *_args: modifications.append((sl, tp)) or True
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
        return strategy, position, market_closes, modifications

    def test_bid_at_or_below_tsl_closes_at_market_before_exit_bracket(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tick = SimpleNamespace(bid=28_884.0, ask=28_885.0)
            strategy, position, market_closes, modifications = self.make_strategy(temp_dir, tick)
            result = strategy.apply_standard_protection(
                position, datetime(2026, 7, 23, 0, 0, tzinfo=WARSAW)
            )
            self.assertTrue(result)
            self.assertEqual(market_closes, ["TSL"])
            self.assertEqual(modifications, [])

    def test_bid_above_tsl_but_too_close_keeps_hard_sl_and_defers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tick = SimpleNamespace(bid=28_890.0, ask=28_891.0)
            strategy, position, market_closes, modifications = self.make_strategy(temp_dir, tick)
            result = strategy.apply_standard_protection(
                position, datetime(2026, 7, 23, 0, 0, tzinfo=WARSAW)
            )
            self.assertTrue(result)
            self.assertTrue(strategy.tsl_install_deferred)
            self.assertEqual(position.sl, 27_550.0)
            self.assertEqual(market_closes, [])
            self.assertEqual(modifications, [])

    def test_deferred_tsl_installs_when_bid_rises_enough(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tick = SimpleNamespace(bid=28_890.0, ask=28_891.0)
            strategy, position, market_closes, modifications = self.make_strategy(temp_dir, tick)
            now = datetime(2026, 7, 23, 0, 0, tzinfo=WARSAW)
            strategy.apply_standard_protection(position, now)
            tick.bid = 28_900.0
            tick.ask = 28_901.0
            result = strategy.apply_standard_protection(position, now)
            self.assertTrue(result)
            self.assertFalse(strategy.tsl_install_deferred)
            self.assertEqual(market_closes, [])
            self.assertEqual(modifications, [(28_884.0, 0.0)])

    def test_existing_tsl_inside_freeze_distance_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tick = SimpleNamespace(bid=28_890.0, ask=28_891.0)
            strategy, position, market_closes, modifications = self.make_strategy(temp_dir, tick)
            position.sl = 28_884.0
            result = strategy.apply_standard_protection(
                position, datetime(2026, 7, 23, 0, 0, tzinfo=WARSAW)
            )
            self.assertTrue(result)
            self.assertFalse(strategy.tsl_install_deferred)
            self.assertEqual(market_closes, [])
            self.assertEqual(modifications, [(28_884.0, 0.0)])

    def test_modify_sltp_does_not_revalidate_or_lower_identical_active_sl(self):
        strategy = object.__new__(MODULE.OPPWContinuousStrategy)
        strategy.state = MODULE.StrategyState(first_protection_confirmed=True)
        strategy.cfg = SimpleNamespace()
        strategy.trade_request_role_allowed = lambda _event: True
        strategy.latest_tick = lambda _symbol: self.fail("identical active SL must not be revalidated")
        strategy.record_active_protection = lambda *_args, **_kwargs: None
        strategy.execution_stage = lambda *_args, **_kwargs: None
        MT5.symbol_info = lambda _symbol: SimpleNamespace(
            trade_tick_size=0.25,
            point=0.25,
            digits=2,
        )
        position = SimpleNamespace(
            ticket=123,
            symbol="US100",
            sl=28_884.0,
            tp=0.0,
        )
        result = strategy.modify_sltp(position, 28_884.0, 0.0, "TSL", "TSL", "")
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
