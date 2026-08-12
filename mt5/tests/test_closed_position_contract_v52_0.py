import importlib.util
from datetime import UTC, datetime
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
mt5.DEAL_TYPE_SELL = 1
mt5.DEAL_REASON_SL = 4
mt5.DEAL_REASON_TP = 5

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

    def test_bh_reason_is_paired_with_bh_price_when_sl_is_also_installed(self):
        strategy = self.strategy(
            active_tp_reason="BH",
            active_tp_price=99.6,
            active_sl_reason="SL",
            active_sl_price=93.75,
        )

        reason, exit_price, change = strategy.closed_position_contract()

        self.assertEqual("BH", reason)
        self.assertAlmostEqual(99.6, exit_price)
        self.assertAlmostEqual(-0.004, change)

    def test_disappeared_position_uses_exact_tp_deal_and_publishes_exit_fill(self):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        state_path = Path("state.json")
        strategy.cfg = SimpleNamespace(state_file=state_path, tsl_stop=0.004)
        strategy.tz = UTC
        strategy.state = MODULE.StrategyState(
            active_position_identifier=2184944,
            active_position_ticket=2184944,
            active_execution_id="execution",
            entry_price=29_797.5,
            open_date="2026-08-10",
            active_tp_reason="BH",
            active_tp_price=29_678.31,
            active_sl_reason="SL",
            active_sl_price=27_936.0,
        )
        strategy.state.save = Mock()
        strategy.log = Mock()
        strategy.execution_stage = Mock()
        closed_at = datetime(2026, 8, 12, 6, 42, 1, 125000, tzinfo=UTC)
        deal = SimpleNamespace(
            ticket=2017001,
            order=2184944,
            position_id=2184944,
            type=mt5.DEAL_TYPE_SELL,
            reason=mt5.DEAL_REASON_TP,
            price=29_678.31,
            volume=0.34,
            time=int(closed_at.timestamp()),
            time_msc=int(closed_at.timestamp() * 1000),
        )
        mt5.history_deals_get = Mock(return_value=(deal,))

        self.assertTrue(strategy.finalize_closed_position())

        mt5.history_deals_get.assert_called_once_with(position=2184944)
        exit_fill = next(
            call for call in strategy.execution_stage.call_args_list
            if call.args and call.args[0] == "EXIT_FILLED"
        )
        self.assertEqual("BH", exit_fill.kwargs["reason"])
        self.assertEqual(2017001, exit_fill.kwargs["deal_ticket"])
        self.assertAlmostEqual(29_678.31, exit_fill.kwargs["actual_price"])
        self.assertAlmostEqual(29_678.31, exit_fill.kwargs["reference_price"])
        self.assertEqual(closed_at.isoformat(), exit_fill.kwargs["event_at"])
        self.assertEqual("BH", strategy.state.last_exit_reason)
        self.assertAlmostEqual(29_678.31, strategy.state.last_exit_price)
        self.assertEqual(2017001, strategy.state.last_exit_deal_ticket)
        self.assertEqual(0, strategy.state.active_position_identifier)

    def test_exact_deal_already_published_by_market_exit_is_not_duplicated(self):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.cfg = SimpleNamespace(state_file=Path("state.json"), tsl_stop=0.004)
        strategy.tz = UTC
        strategy.state = MODULE.StrategyState(
            active_position_identifier=123,
            active_position_ticket=123,
            entry_price=100.0,
            exit_latched_reason="TSL1PRE",
            last_exit_price=95.165,
            last_exit_deal_ticket=1994541,
        )
        strategy.state.save = Mock()
        strategy.log = Mock()
        strategy.execution_stage = Mock()
        closed_at = datetime(2026, 7, 30, 14, 0, tzinfo=UTC)
        mt5.history_deals_get = Mock(return_value=(SimpleNamespace(
            ticket=1994541, order=2160777, position_id=123,
            type=mt5.DEAL_TYPE_SELL, reason=0, price=95.165, volume=0.64,
            time=int(closed_at.timestamp()), time_msc=int(closed_at.timestamp() * 1000),
        ),))

        self.assertTrue(strategy.finalize_closed_position())

        stages = [call.args[0] for call in strategy.execution_stage.call_args_list]
        self.assertNotIn("EXIT_FILLED", stages)
        self.assertEqual(["CLOSED"], stages)

    def test_missing_exact_deal_defers_reconciliation_without_clearing_state(self):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.cfg = SimpleNamespace(state_file=Path("state.json"), tsl_stop=0.004)
        strategy.tz = UTC
        strategy.state = MODULE.StrategyState(
            active_position_identifier=777,
            active_position_ticket=778,
            entry_price=100.0,
            active_tp_reason="BH",
            active_tp_price=99.6,
            active_sl_reason="SL",
            active_sl_price=93.75,
        )
        strategy.log = Mock()
        strategy.execution_stage = Mock()
        mt5.history_deals_get = Mock(return_value=())

        self.assertFalse(strategy.finalize_closed_position())

        self.assertEqual(777, strategy.state.active_position_identifier)
        strategy.execution_stage.assert_not_called()
        strategy.log.warning.assert_called_once()

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
            last_exit_deal_ticket=0,
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
        self.assertEqual(1994541, strategy.state.last_exit_deal_ticket)
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
