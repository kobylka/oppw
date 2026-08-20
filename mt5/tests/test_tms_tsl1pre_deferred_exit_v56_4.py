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
from unittest.mock import Mock


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    mt5.ORDER_TYPE_BUY = 0
    mt5.ORDER_TYPE_SELL = 1
    mt5.POSITION_TYPE_BUY = 0
    mt5.TRADE_ACTION_DEAL = 1
    mt5.ORDER_TIME_GTC = 0
    mt5.last_error = lambda: (0, "")
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
    spec = importlib.util.spec_from_file_location("oppw_v56_4_tms_tsl1pre_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()
MT5 = sys.modules["MetaTrader5"]
WARSAW = ZoneInfo("Europe/Warsaw")


class TmsTsl1PreDeferredExitTests(unittest.TestCase):
    def strategy(self, temp_dir: str):
        strategy = MODULE.OPPWContinuousStrategy.__new__(MODULE.OPPWContinuousStrategy)
        strategy.tz = WARSAW
        strategy.account = "DEMO_TMS"
        strategy.role = "EXECUTOR"
        strategy.cfg = SimpleNamespace(
            state_file=Path(temp_dir) / "state.json",
            timezone_name="Europe/Warsaw",
            tsl1pre_market_exit_delay_seconds=60.0,
        )
        strategy.state = MODULE.StrategyState(
            active_position_identifier=777,
            active_position_ticket=123,
            exit_latched_reason="",
        )
        strategy.position_rule_controls = {"OR5": False}
        strategy.position_rule_controls_revision = 1
        strategy.position_rule_observed_after_utc = 0
        strategy.last_position_rule_context_success_monotonic = 0.0
        strategy.local_to_mt5_bar_query_time = lambda value: value
        strategy.log = SimpleNamespace(
            info=lambda *_args, **_kwargs: None,
            warning=lambda *_args, **_kwargs: None,
            error=lambda *_args, **_kwargs: None,
        )
        strategy.execution_stage = lambda *_args, **_kwargs: None
        return strategy

    @staticmethod
    def position():
        return SimpleNamespace(
            identifier=777, ticket=123, symbol="US100.pro", price_open=29_000.0, volume=0.02,
        )

    @staticmethod
    def trigger_payload(now: datetime):
        return {
            "positionRevision": 1,
            "positionRules": [{"key": "OR5", "enabled": False}],
            "positionTrigger": {
                "requestId": "a" * 32,
                "ruleKey": "TSL1PRE",
                "positionIdentifier": 777,
                "positionTicket": 123,
                "signalAt": now.isoformat(),
                "recordedAt": now.isoformat(),
                "inputs": {
                    "triggeredAt": now.isoformat(),
                    "notBefore": "2026-08-20T00:01:00+02:00",
                    "referenceBid": 28_884.0,
                    "tslThreshold": 28_884.0,
                    "delaySeconds": 60.0,
                },
            },
        }

    def test_cross_at_midnight_is_authorized_but_not_submitted_before_0001(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(temp_dir)
            position = self.position()
            now = datetime(2026, 8, 20, 0, 0, 1, tzinfo=WARSAW)
            payload = self.trigger_payload(now)

            def authorize(*_args):
                strategy.apply_position_rule_context(payload)
                return payload

            strategy.record_tsl1pre_trigger = authorize
            closes = []
            strategy.close_position_market = lambda *_args: closes.append(_args[1]) or False

            handled = strategy.arm_tsl1pre_market_exit(position, now, 28_884.0, 28_884.0)

            self.assertTrue(handled)
            self.assertEqual([], closes)
            self.assertEqual("TSL1PRE", strategy.state.exit_latched_reason)
            self.assertEqual("2026-08-20T00:01:00+02:00", strategy.state.pending_market_exit_not_before)
            self.assertEqual(777, strategy.state.pending_market_exit_position_identifier)

    def test_market_closed_rejection_keeps_market_intent_and_retries_after_0001(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(temp_dir)
            position = self.position()
            triggered = datetime(2026, 8, 20, 0, 0, 1, tzinfo=WARSAW)
            strategy.apply_position_rule_context(self.trigger_payload(triggered))
            bracket_calls = []
            market_calls = []
            strategy.apply_exit_bracket = lambda *_args: bracket_calls.append(_args) or True
            strategy.close_position_market = lambda *_args: market_calls.append(_args[1]) or False
            due = datetime(2026, 8, 20, 0, 1, 0, tzinfo=WARSAW)

            first = strategy.apply_standard_protection(position, due)
            second = strategy.apply_standard_protection(position, due)

            self.assertFalse(first)
            self.assertFalse(second)
            self.assertEqual(["TSL1PRE", "TSL1PRE"], market_calls)
            self.assertEqual([], bracket_calls)
            self.assertEqual("TSL1PRE", strategy.state.pending_market_exit_reason)
            self.assertEqual("TSL1PRE", strategy.state.exit_latched_reason)

    def test_pending_intent_survives_state_reload_and_price_recovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(temp_dir)
            triggered = datetime(2026, 8, 20, 0, 0, 1, tzinfo=WARSAW)
            strategy.apply_position_rule_context(self.trigger_payload(triggered))
            strategy.state.save(strategy.cfg.state_file)

            restored = MODULE.StrategyState.load(strategy.cfg.state_file)

            self.assertEqual("TSL1PRE", restored.pending_market_exit_reason)
            self.assertEqual(777, restored.pending_market_exit_position_identifier)
            self.assertEqual("a" * 32, restored.pending_market_exit_request_id)
            self.assertEqual("2026-08-20T00:01:00+02:00", restored.pending_market_exit_not_before)

    def test_retcode_10018_remains_exit_rejected_and_retries_market_sell(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            strategy = self.strategy(temp_dir)
            strategy.cfg.live_enabled = True
            strategy.cfg.deviation_points = 50
            strategy.cfg.magic = 24001
            strategy.cfg.comment_prefix = "OPPW"
            strategy.cfg.market_order_priority_delay_seconds = 0.0
            position = self.position()
            triggered = datetime(2026, 8, 20, 0, 0, 1, tzinfo=WARSAW)
            strategy.apply_position_rule_context(self.trigger_payload(triggered))
            strategy.trade_request_role_allowed = Mock(return_value=True)
            strategy.require_fresh_tick = Mock(return_value=SimpleNamespace(bid=28_883.0))
            strategy.ensure_autotrading_enabled = Mock(return_value=True)
            strategy.request_allowed_now = Mock(return_value=True)
            strategy.checked_deal_request = Mock(
                return_value=({"type_filling": 0}, SimpleNamespace(retcode=0))
            )
            strategy.filling_mode_name = Mock(return_value="FOK")
            strategy.execution_stage = Mock()
            strategy.apply_exit_bracket = Mock(side_effect=AssertionError("pending market exit must not become a bracket"))
            strategy.coordinator = SimpleNamespace(
                acquire_trade_gate=lambda *_args: object(),
                validate_trade_gate=lambda *_args: None,
                release_trade_gate=lambda *_args: None,
            )
            MT5.symbol_info = Mock(return_value=SimpleNamespace())
            MT5.order_send = Mock(return_value=SimpleNamespace(
                retcode=10018, price=0.0, order=0, deal=0, comment="Market closed",
            ))
            due = datetime(2026, 8, 20, 0, 1, 0, tzinfo=WARSAW)

            first = strategy.close_position_market(position, "TSL1PRE", due)
            second = strategy.apply_standard_protection(position, due)

            self.assertFalse(first)
            self.assertFalse(second)
            self.assertEqual(2, MT5.order_send.call_count)
            strategy.apply_exit_bracket.assert_not_called()
            self.assertEqual("TSL1PRE", strategy.state.pending_market_exit_reason)
            rejected = [
                call for call in strategy.execution_stage.call_args_list
                if call.args and call.args[0] == "EXIT_ACCEPTED" and call.kwargs.get("result") is False
            ]
            self.assertEqual(2, len(rejected))
            self.assertTrue(all(call.kwargs.get("retcode") == 10018 for call in rejected))


if __name__ == "__main__":
    unittest.main()
