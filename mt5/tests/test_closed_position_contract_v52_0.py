import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
mt5.ORDER_TYPE_BUY = 0
mt5.ORDER_TYPE_SELL = 1
mt5.POSITION_TYPE_BUY = 0
mt5.POSITION_TYPE_SELL = 1
mt5.TRADE_ACTION_DEAL = 1
mt5.ORDER_TIME_GTC = 0
mt5.TRADE_RETCODE_DONE = 10009
mt5.TRADE_RETCODE_PLACED = 10008
mt5.TRADE_RETCODE_DONE_PARTIAL = 10010

SOURCE = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
SPEC = importlib.util.spec_from_file_location("oppw_closed_position_contract", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ClosedPositionContractTests(unittest.TestCase):
    def strategy(self, **state_values):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.cfg = SimpleNamespace(tsl_stop=0.004)
        defaults = dict(
            exit_latched_reason="",
            active_tp_reason="",
            active_sl_reason="",
            active_tp_price=0.0,
            active_sl_price=0.0,
            last_exit_price=0.0,
            entry_price=100.0,
        )
        defaults.update(state_values)
        strategy.state = SimpleNamespace(**defaults)
        return strategy

    def test_tsl_uses_installed_stop_not_later_quote(self):
        strategy = self.strategy(active_sl_reason="TSL", active_sl_price=99.6, last_exit_price=98.8552)

        reason, exit_price, change = strategy.closed_position_contract()

        self.assertEqual("TSL_0.4%", reason)
        self.assertAlmostEqual(99.6, exit_price)
        self.assertAlmostEqual(-0.004, change)
        self.assertEqual("C", strategy.trade_class(change, reason))

    def test_latched_market_exit_keeps_recorded_exit_price(self):
        strategy = self.strategy(
            exit_latched_reason="TSL1PRE",
            last_exit_price=95.165,
            active_sl_reason="SL",
            active_sl_price=95.0,
        )

        reason, exit_price, change = strategy.closed_position_contract()

        self.assertEqual("TSL1PRE", reason)
        self.assertAlmostEqual(95.165, exit_price)
        self.assertAlmostEqual(-0.04835, change)
        self.assertEqual("C", strategy.trade_class(change, reason))

    def test_confirmed_market_exit_persists_exact_deal_price(self):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.cfg = SimpleNamespace(
            live_enabled=True,
            deviation_points=50,
            magic=24001,
            comment_prefix="OPPW",
            state_file=Path("state.json"),
        )
        strategy.state = SimpleNamespace(
            exit_latched_reason="",
            exit_latched_at="",
            last_exit_price=0.0,
            save=Mock(),
        )
        strategy.log = Mock()
        strategy.trade_request_role_allowed = Mock(return_value=True)
        strategy.require_fresh_tick = Mock(return_value=SimpleNamespace(bid=95.2))
        strategy.ensure_autotrading_enabled = Mock(return_value=True)
        strategy.request_allowed_now = Mock(return_value=True)
        strategy.checked_deal_request = Mock(
            return_value=({"type_filling": 0}, SimpleNamespace(retcode=0))
        )
        strategy.filling_mode_name = Mock(return_value="FOK")
        strategy.execution_stage = Mock()
        strategy.coordinator = SimpleNamespace(
            acquire_trade_gate=lambda *_args: object(),
            validate_trade_gate=lambda *_args: None,
            release_trade_gate=lambda *_args: None,
        )
        position = SimpleNamespace(ticket=123, symbol="US100", volume=0.64)
        mt5.symbol_info = Mock(return_value=SimpleNamespace())
        mt5.order_send = Mock(return_value=SimpleNamespace(
            retcode=10009,
            price=95.165,
            order=2160777,
            deal=1994541,
            comment="done",
        ))

        result = strategy.close_position_market(
            position, "TSL1PRE", MODULE.datetime(2026, 7, 30, tzinfo=MODULE.UTC)
        )

        self.assertTrue(result)
        self.assertEqual("TSL1PRE", strategy.state.exit_latched_reason)
        self.assertAlmostEqual(95.165, strategy.state.last_exit_price)
        self.assertGreaterEqual(strategy.state.save.call_count, 2)
        self.assertTrue(any(
            call.args and call.args[0] == "EXIT_FILLED"
            for call in strategy.execution_stage.call_args_list
        ))

    @patch.object(MODULE.time_module, "sleep")
    @patch.object(MODULE.StrategyState, "load")
    def test_publisher_retries_transient_windows_state_permission_error(self, load, sleep):
        recovered = SimpleNamespace(version=7)
        load.side_effect = [PermissionError("sharing violation"), recovered]
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.cfg = SimpleNamespace(state_file=Path("state.json"))
        strategy.state = SimpleNamespace(version=6)
        strategy.log = Mock()

        strategy.reload_state_read_only()

        self.assertIs(recovered, strategy.state)
        self.assertEqual(2, load.call_count)
        sleep.assert_called_once_with(0.05)
        strategy.log.info.assert_called_once()
        strategy.log.warning.assert_not_called()

    def test_recalculated_decisions_cannot_reuse_immutable_identifier(self):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.account = "REAL"
        strategy.tz = MODULE.UTC
        strategy.strategy_specification = {"specId": "a" * 32, "specHash": "b" * 64}
        strategy.strategy_decision_week_key = lambda now=None: "2026-W30"
        strategy.strategy_parameter_hash = lambda: "c" * 64
        preview = {
            "symbol": "US100", "strategyLeverage": 10.0, "previousFullWeekChange": -0.03,
            "previousTradeChange": -0.004, "volume": 0.01, "available": True,
            "balance": 7647.92, "sizingFreeMargin": 7647.92,
        }

        first = strategy.strategy_decision_payload(preview)
        MODULE.time_module.sleep(0.001)
        second = strategy.strategy_decision_payload(preview)

        self.assertNotEqual(first["recordedAt"], second["recordedAt"])
        self.assertNotEqual(first["decisionId"], second["decisionId"])

    @patch.object(MODULE.time_module, "sleep")
    @patch.object(MODULE.os, "replace")
    def test_state_save_retries_transient_windows_replace_denial(self, replace, sleep):
        replace.side_effect = [PermissionError("sharing violation"), None]

        with patch.object(MODULE.Path, "write_text"):
            MODULE.StrategyState().save(Path("state.json"))

        self.assertEqual(2, replace.call_count)
        sleep.assert_called_once_with(0.05)

    def test_repeated_flat_snapshots_reuse_last_recorded_decision(self):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        recorded = {"decisionId": "immutable-decision"}
        strategy.last_strategy_decision_payload = recorded
        strategy.record_strategy_decision_if_changed = Mock(side_effect=AssertionError("must not regenerate"))

        first = strategy.snapshot_strategy_decision(None, {"price": 100.0})
        second = strategy.snapshot_strategy_decision(None, {"price": 101.0})

        self.assertIs(recorded, first)
        self.assertIs(recorded, second)
        strategy.record_strategy_decision_if_changed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
