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
    spec = importlib.util.spec_from_file_location("oppw_v49_immutable_stop_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()
MT5 = sys.modules["MetaTrader5"]
WARSAW = ZoneInfo("Europe/Warsaw")


class ImmutableHardStopTests(unittest.TestCase):
    def position(self, *, sl=0.0, magic=240024):
        return SimpleNamespace(
            identifier=777,
            ticket=123,
            symbol="US100",
            price_open=29_000.0,
            price_current=29_100.0,
            volume=0.02,
            sl=sl,
            tp=0.0,
            comment="OPPW L10",
            magic=magic,
            type=0,
        )

    def strategy(self, state_file: Path):
        strategy = object.__new__(MODULE.OPPWContinuousStrategy)
        strategy.state = MODULE.StrategyState(
            active_position_identifier=777,
            active_position_ticket=123,
            entry_price=29_000.0,
            entry_leverage=10,
        )
        strategy.cfg = SimpleNamespace(
            state_file=state_file,
            tsl_stop=0.004,
            tsl_ratio=0.996,
            break_even_ratio=0.996,
            base_leverage=8,
            loss_leverage=10,
            leverage_stop_points=50.0,
            full_week_loss_trigger=-0.025,
            previous_trade_loss_trigger=-0.002,
            magic=240024,
        )
        strategy.log = SimpleNamespace(
            info=lambda *_args, **_kwargs: None,
            warning=lambda *_args, **_kwargs: None,
        )
        strategy.tz = WARSAW
        return strategy

    def test_definitive_stop_is_locked_once_and_ignores_later_balance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(Path(temp_dir) / "state.json")
            position = self.position()
            account = SimpleNamespace(balance=8_000.0, currency="PLN")
            MT5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)
            MT5.account_info = lambda: account
            MT5.order_calc_profit = lambda *_args: -4_000.0
            calculated = [27_550.0]
            strategy.capped_hard_stop = lambda *_args: (calculated[0], -4_000.0, True)

            now = datetime(2026, 7, 20, 15, 30, tzinfo=WARSAW)
            self.assertTrue(strategy.lock_immutable_hard_stop(position, now, "POST_FILL"))
            self.assertEqual(strategy.state.immutable_hard_sl_price, 27_550.0)
            self.assertEqual(strategy.state.immutable_hard_sl_balance, 8_000.0)

            account.balance = 20_000.0
            calculated[0] = 26_000.0
            self.assertFalse(strategy.lock_immutable_hard_stop(position, now, "SHOULD_NOT_REPRICE"))
            self.assertEqual(strategy.state.immutable_hard_sl_price, 27_550.0)
            self.assertEqual(strategy.state.immutable_hard_sl_balance, 8_000.0)
            self.assertEqual(strategy.state.immutable_hard_sl_source, "POST_FILL")

            restored = MODULE.StrategyState.load(strategy.cfg.state_file)
            self.assertEqual(restored.immutable_hard_sl_price, 27_550.0)
            self.assertEqual(restored.immutable_hard_sl_position_identifier, 777)

    def test_hard_sl_reader_never_recalculates_locked_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(Path(temp_dir) / "state.json")
            strategy.state.immutable_hard_sl_position_identifier = 777
            strategy.state.immutable_hard_sl_price = 27_550.0
            MT5.account_info = lambda: self.fail("account_info must not be read for a locked baseline")
            self.assertEqual(strategy.hard_sl_price(self.position()), 27_550.0)

    def test_manual_position_without_comment_uses_loss_leverage_decision_for_stop_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(Path(temp_dir) / "state.json")
            strategy.state.active_position_identifier = 999
            strategy.state.active_position_ticket = 999
            strategy.state.entry_price = 30_000.0
            strategy.state.entry_leverage = 10
            position = self.position(magic=0)
            position.comment = "manual"
            strategy.resolved_leverage_inputs = lambda: (-0.03, 0.0, "test market history", "test trade history")
            MT5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)

            leverage, source, reason = strategy.resolve_position_leverage(position)
            self.assertEqual(leverage, 10)
            self.assertEqual(source, "strategy_decision")
            self.assertIn("-3.0000%", reason)
            self.assertEqual(strategy.hard_sl_price(position), 27_550.0)
            target = strategy.protection_target_payload(
                position, datetime(2026, 7, 20, 12, 0, tzinfo=WARSAW),
            )
            self.assertEqual(target["price"], 27_550.0)
            self.assertFalse(target["applied"])
            self.assertTrue(target["executorRequired"])
            self.assertEqual(target["source"], "PENDING_EXECUTOR_HARD_STOP")

    def test_wrong_l8_recovery_lock_is_corrected_once_to_authoritative_l10(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(Path(temp_dir) / "state.json")
            position = self.position(sl=27_188.0, magic=0)
            position.comment = "manual"
            strategy.state.entry_leverage = 8
            strategy.state.immutable_hard_sl_position_identifier = 777
            strategy.state.immutable_hard_sl_price = 27_188.0
            strategy.state.immutable_hard_sl_entry_price = 29_000.0
            strategy.state.immutable_hard_sl_volume = 0.02
            strategy.state.immutable_hard_sl_balance = 8_000.0
            strategy.state.immutable_hard_sl_leverage = 8
            strategy.state.immutable_hard_sl_source = "POST_FILL"
            strategy.state.first_protection_confirmed = True
            MT5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)
            MT5.account_info = lambda: SimpleNamespace(balance=9_000.0, currency="PLN")
            MT5.order_calc_profit = lambda *_args: -4_000.0
            captured_balances = []
            strategy.capped_hard_stop = lambda _symbol, _volume, _entry, balance, leverage, _tick: (
                captured_balances.append((balance, leverage)) or (27_550.0, -4_000.0, True)
            )

            self.assertTrue(strategy.repair_recovery_hard_stop_leverage(
                position, datetime(2026, 7, 20, 16, 0, tzinfo=WARSAW), 10,
            ))
            self.assertEqual(captured_balances, [(8_000.0, 10)])
            self.assertEqual(strategy.state.entry_leverage, 10)
            self.assertEqual(strategy.state.immutable_hard_sl_leverage, 10)
            self.assertEqual(strategy.state.immutable_hard_sl_price, 27_550.0)
            self.assertEqual(strategy.state.immutable_hard_sl_source, "RECOVERY_LEVERAGE_CORRECTION")
            self.assertFalse(strategy.state.first_protection_confirmed)
            self.assertFalse(strategy.repair_recovery_hard_stop_leverage(
                position, datetime(2026, 7, 20, 16, 1, tzinfo=WARSAW), 10,
            ))

    def test_manual_recovery_clears_stale_strategy_execution_link(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(Path(temp_dir) / "state.json")
            strategy.state.active_execution_id = "stale-execution"
            strategy.state.active_decision_id = "stale-decision"
            strategy.state.active_strategy_spec_id = "stale-spec"
            strategy.state.active_strategy_spec_hash = "stale-hash"
            strategy.state.execution_scheduled_at = "2026-07-20T15:30:00+02:00"
            strategy.state.execution_started_at = "2026-07-20T15:29:59+02:00"
            strategy.state.execution_fill_confirmed = True
            strategy.state.execution_position_visible = True

            self.assertTrue(strategy.clear_stale_execution_link_for_manual_position(
                self.position(magic=0)
            ))
            self.assertEqual(strategy.state.active_execution_id, "")
            self.assertEqual(strategy.state.active_decision_id, "")
            self.assertEqual(strategy.state.active_strategy_spec_id, "")
            self.assertEqual(strategy.state.active_strategy_spec_hash, "")
            self.assertEqual(strategy.state.execution_scheduled_at, "")
            self.assertEqual(strategy.state.execution_started_at, "")
            self.assertFalse(strategy.state.execution_fill_confirmed)
            self.assertFalse(strategy.state.execution_position_visible)

            strategy.state.active_execution_id = "strategy-execution"
            self.assertFalse(strategy.clear_stale_execution_link_for_manual_position(
                self.position(magic=240024)
            ))
            self.assertEqual(strategy.state.active_execution_id, "strategy-execution")

    def test_thursday_tsl_can_only_tighten_immutable_stop(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(Path(temp_dir) / "state.json")
            strategy.state.immutable_hard_sl_position_identifier = 777
            strategy.state.immutable_hard_sl_price = 27_550.0
            target, reason = strategy.weekday_sl_target(
                self.position(), datetime(2026, 7, 23, 0, 0, tzinfo=WARSAW)
            )
            self.assertEqual(reason, "TSL")
            self.assertEqual(target, 29_000.0 * 0.996)
            self.assertGreater(target, strategy.state.immutable_hard_sl_price)

    def test_missing_broker_sl_restores_immutable_price_without_repricing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(Path(temp_dir) / "state.json")
            strategy.state.immutable_hard_sl_position_identifier = 777
            strategy.state.immutable_hard_sl_price = 27_550.0
            strategy.state.immutable_hard_sl_leverage = 10
            strategy.state.first_protection_confirmed = True
            strategy.state.exit_latched_reason = ""
            strategy.state.break_even = False
            strategy.immutable_hard_stop_matches = lambda _position: True
            strategy.lock_immutable_hard_stop = lambda *_args: self.fail("locked stop must not be recalculated")
            strategy.weekday_sl_target = lambda _position, _now: (27_550.0, "SL")
            strategy.fresh_tick_for_protection = lambda *_args: SimpleNamespace(bid=29_100.0, ask=29_101.0)
            strategy.broker_minimum_distance = lambda _info: 1.0
            captured = []
            strategy.modify_sltp = lambda _position, sl, tp, reason, sl_reason, tp_reason: captured.append(
                (sl, tp, reason, sl_reason, tp_reason)
            ) or True
            MT5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)

            result = strategy.apply_standard_protection(
                self.position(sl=0.0), datetime(2026, 7, 21, 12, 0, tzinfo=WARSAW)
            )
            self.assertTrue(result)
            self.assertEqual(captured[0][0], 27_550.0)
            self.assertIn("IMMUTABLE_HARD_SL", captured[0][2])

    def test_first_post_fill_pass_may_correct_provisional_stop_downward(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(Path(temp_dir) / "state.json")
            strategy.state.immutable_hard_sl_position_identifier = 777
            strategy.state.immutable_hard_sl_price = 27_550.0
            strategy.state.immutable_hard_sl_leverage = 10
            strategy.state.first_protection_confirmed = False
            strategy.state.exit_latched_reason = ""
            strategy.state.break_even = False
            strategy.immutable_hard_stop_matches = lambda _position: True
            strategy.weekday_sl_target = lambda _position, _now: (27_550.0, "SL")
            strategy.fresh_tick_for_protection = lambda *_args: SimpleNamespace(bid=29_100.0, ask=29_101.0)
            strategy.broker_minimum_distance = lambda _info: 1.0
            captured = []
            strategy.modify_sltp = lambda _position, sl, *_args: captured.append(sl) or True
            MT5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)

            strategy.apply_standard_protection(
                self.position(sl=27_600.0), datetime(2026, 7, 21, 12, 0, tzinfo=WARSAW)
            )
            self.assertEqual(captured, [27_550.0])

    def test_confirmed_tighter_stop_is_never_weakened(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(Path(temp_dir) / "state.json")
            strategy.state.immutable_hard_sl_position_identifier = 777
            strategy.state.immutable_hard_sl_price = 27_550.0
            strategy.state.immutable_hard_sl_leverage = 10
            strategy.state.first_protection_confirmed = True
            strategy.state.exit_latched_reason = ""
            strategy.state.break_even = False
            strategy.state.active_sl_reason = "TSL"
            strategy.immutable_hard_stop_matches = lambda _position: True
            strategy.weekday_sl_target = lambda _position, _now: (27_550.0, "SL")
            strategy.fresh_tick_for_protection = lambda *_args: SimpleNamespace(bid=29_100.0, ask=29_101.0)
            strategy.broker_minimum_distance = lambda _info: 1.0
            captured = []
            strategy.modify_sltp = lambda _position, sl, *_args: captured.append(sl) or True
            MT5.symbol_info = lambda _symbol: SimpleNamespace(trade_tick_size=0.25, point=0.25)

            strategy.apply_standard_protection(
                self.position(sl=28_000.0), datetime(2026, 7, 21, 12, 0, tzinfo=WARSAW)
            )
            self.assertEqual(captured, [28_000.0])

    def test_manual_recovery_applies_protection_before_other_cycle_logic(self):
        strategy = object.__new__(MODULE.OPPWContinuousStrategy)
        position = self.position(sl=0.0)
        actions = []
        strategy.is_executor = True
        strategy.tz = WARSAW
        strategy.cfg = SimpleNamespace(trade_symbol="US100")
        strategy.state = SimpleNamespace(active_position_identifier=0)
        strategy.coordinator = SimpleNamespace(require_role_lease=lambda: None)
        strategy.is_weekend = lambda _now: False
        strategy.ensure_autotrading_enabled = lambda _context: True
        strategy.log_week_plan = lambda _day: None
        strategy.managed_position = lambda: position

        def recover(_position, _now):
            strategy.state.active_position_identifier = 777
            actions.append("recover")
            return True

        strategy.recover_position_state = recover
        strategy.apply_standard_protection = lambda _position, _now: actions.append("protect") or True
        strategy.emit_status = lambda *_args: actions.append("emit")
        strategy.current_m1_bar = lambda _symbol: actions.append("current_bar") or None
        strategy.capture_entry_signal_open = lambda *_args: False
        strategy.maybe_execute_open_action = lambda *_args: False
        strategy.maybe_execute_close_action = lambda *_args: False
        strategy.session_times = lambda _day: SimpleNamespace(
            cash_open=datetime(2099, 1, 1, tzinfo=WARSAW),
            close_processing=datetime(2099, 1, 1, tzinfo=WARSAW),
        )
        strategy.publish_account_change_if_needed = lambda *_args: False
        strategy.log_status_if_needed = lambda *_args: None
        strategy.publish_mobile_minute_status = lambda *_args: False
        strategy.publish_mobile_if_due = lambda *_args: None

        strategy.cycle()

        self.assertEqual(actions[:3], ["recover", "protect", "emit"])
        self.assertLess(actions.index("protect"), actions.index("current_bar"))


class BreakEvenMarketExitTests(unittest.TestCase):
    def strategy(self):
        calls = []
        strategy = SimpleNamespace(
            state=SimpleNamespace(
                break_even=True,
                exit_latched_reason="",
                last_close_action_date="",
            ),
            cfg=SimpleNamespace(break_even_ratio=0.996),
            close_position_market=lambda _position, reason, _now: calls.append(reason) or True,
        )
        return strategy, calls

    def test_bepre_uses_market_sell_path(self):
        strategy, calls = self.strategy()
        position = SimpleNamespace(price_open=100.0)
        bar = SimpleNamespace(open=100.0)
        MODULE.OPPWContinuousStrategy.evaluate_premarket_open(
            strategy, position, bar, datetime(2026, 7, 21, 8, 0, tzinfo=WARSAW)
        )
        self.assertEqual(calls, ["BEPRE"])

    def test_beo_uses_market_sell_path(self):
        strategy, calls = self.strategy()
        position = SimpleNamespace(price_open=100.0)
        bar = SimpleNamespace(open=100.0)
        MODULE.OPPWContinuousStrategy.evaluate_cash_open(
            strategy, position, bar, datetime(2026, 7, 21, 15, 30, tzinfo=WARSAW)
        )
        self.assertEqual(calls, ["BEO"])

    def test_bh_uses_market_sell_path(self):
        strategy, calls = self.strategy()
        position = SimpleNamespace(price_open=100.0)
        bar = SimpleNamespace(
            high=100.0,
            local_datetime=datetime(2026, 7, 21, 16, 0, tzinfo=WARSAW),
        )
        MODULE.OPPWContinuousStrategy.evaluate_regular_bar(
            strategy, position, bar, datetime(2026, 7, 21, 16, 0, tzinfo=WARSAW)
        )
        self.assertEqual(calls, ["BH"])

    def test_removed_crossed_tp_reason_is_absent_from_v49_source(self):
        source = (Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py").read_text(encoding="utf-8")
        removed_reason = "PROTECTION_TP_" + "ALREADY_CROSSED"
        self.assertNotIn(removed_reason, source)


if __name__ == "__main__":
    unittest.main()
