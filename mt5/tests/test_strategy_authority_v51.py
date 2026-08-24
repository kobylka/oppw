from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import sys
import types
import unittest
from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    mt5 = sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    mt5.ORDER_TYPE_BUY = 0
    mt5.ORDER_TYPE_SELL = 1
    mt5.POSITION_TYPE_BUY = 0
    mt5.POSITION_TYPE_SELL = 1
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
    spec = importlib.util.spec_from_file_location("oppw_v51_authority_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()
WARSAW = ZoneInfo("Europe/Warsaw")


def strategy_config():
    return SimpleNamespace(
        trade_symbol="US100", signal_symbol="US100", exchange_calendar="XNYS",
        timezone_name="Europe/Warsaw", market_timezone_name="America/New_York",
        premarket_start=time(0, 0), cash_open=time(9, 30), close_bar_open=time(16, 0),
        entry_action_lead_seconds=3.0, non_entry_action_lead_seconds=3.0, entry_window_seconds=55,
        market_order_priority_delay_seconds=0.0,
        base_leverage=8, loss_leverage=10, full_week_loss_trigger=-0.025,
        previous_trade_loss_trigger=-0.007, sizing_multiplier=20.0,
        entry_rule_arithmetic_threshold=0.02, entry_rule_gap_threshold=0.01,
        entry_rule_momentum20_threshold=-0.005, entry_rule_tuesday_normalization_tolerance=0.005,
        entry_rule_premarket_minimum_range=0.008, entry_rule_premarket_maximum_close_location=0.15,
        required_balance_multiplier=1.765, legacy_required_balance_multiplier_l10=2.0,
        legacy_required_balance_multiplier_l8=2.5, use_legacy_balance_multiplier=False,
        tpps=(0.007, 0.02, 0.05, 0.05, 0.05), break_even_ratio=0.996,
        tsl_stop=0.004, leverage_stop_points=50.0, hard_stop_ratio_override=0.0,
        max_account_stop_loss_fraction=0.5,
        deviation_points=20, filling_mode="AUTO",
    )


class StrategySpecificationTests(unittest.TestCase):
    def strategy(self):
        strategy = object.__new__(MODULE.OPPWContinuousStrategy)
        strategy.cfg = strategy_config()
        strategy.account = "DEMO"
        strategy.tz = WARSAW
        strategy.started_at = datetime(2026, 7, 21, 12, 0, tzinfo=WARSAW)
        strategy.state = MODULE.StrategyState()
        strategy.entry_rule_controls_revision = 1
        strategy.entry_rule_controls = {
            "ARITHMETIC_LAST_TWO": True, "GAP_MOMENTUM": True,
            "TUESDAY_NORMALIZATION": True, "PREMARKET_LOW": True,
        }
        strategy.cached_previous_full_week_change = 0.0
        strategy.cached_previous_trade_change = 0.0
        strategy.cached_previous_full_week_source = "test"
        strategy.cached_previous_trade_source = "test"
        strategy.strategy_specification = strategy.build_strategy_specification()
        strategy.leverage_decision = lambda: (8, "test")
        strategy.strategy_decision_week_key = lambda now=None: "2026-W30"
        return strategy

    def test_specification_hash_is_canonical_and_complete(self):
        strategy = self.strategy()
        specification = strategy.strategy_specification
        canonical = json.dumps(
            specification["document"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(specification["specHash"], expected)
        self.assertEqual(specification["specId"], expected[:32])
        self.assertEqual(specification["document"]["instruments"]["execution"], "US100")
        self.assertEqual(specification["document"]["instruments"]["signal"], "US100")
        self.assertIn("second actual XNYS session", specification["document"]["thresholds"]["openHighSchedule"])
        self.assertIn("second actual XNYS session", specification["document"]["thresholds"]["breakEvenArmSchedule"])
        self.assertIn("authoritative leverage decision", specification["document"]["leverageSelection"]["manualPositionRule"])
        self.assertIn("detach", specification["document"]["leverageSelection"]["manualRecoveryLinkRule"])
        self.assertIn("recovery leverage correction", specification["document"]["hardStopInvariant"]["allowedTightening"])
        self.assertEqual(specification["document"]["persistenceAuthority"]["events"], "diagnostic stream only")
        self.assertEqual(specification["document"]["entryLossControl"]["arithmeticLookback"], 2)
        self.assertEqual(specification["document"]["entryLossControl"]["momentumSessions"], 20)
        self.assertIn("pre-open entry action", specification["document"]["calendarAndTime"]["ruleControlledEntryTime"])
        self.assertIn("fresh MT5 BUY price", specification["document"]["entryLossControl"]["entryPriceReference"])
        self.assertIn(
            "strictly before",
            specification["document"]["entryLossControl"]["completedSessionCloseReference"],
        )
        self.assertEqual("GROWTH_1_765", specification["document"]["sizing"]["activeProfile"])
        self.assertEqual(0.9375, strategy.hard_sl_ratio(8))
        self.assertEqual(0.95, strategy.hard_sl_ratio(10))

    def test_account_hard_stop_ratio_override_is_leverage_independent_and_audited(self):
        strategy = self.strategy()
        strategy.cfg.hard_stop_ratio_override = 0.9465

        specification = strategy.build_strategy_specification()

        self.assertEqual(0.9465, strategy.hard_sl_ratio(8))
        self.assertEqual(0.9465, strategy.hard_sl_ratio(10))
        self.assertEqual(0.9465, specification["document"]["thresholds"]["hardStopRatioOverride"])
        self.assertEqual(0.9465, specification["document"]["thresholds"]["hardStopRatioL8"])
        self.assertEqual(0.9465, specification["document"]["thresholds"]["hardStopRatioL10"])

    def test_account_required_balance_override_is_effective_and_audited(self):
        strategy = self.strategy()
        strategy.cfg.required_balance_multiplier = 1.5

        specification = strategy.build_strategy_specification()
        sizing = specification["document"]["sizing"]

        self.assertEqual(1.5, strategy.required_balance_multiplier(8))
        self.assertEqual("GROWTH_1_500", strategy.balance_multiplier_profile())
        self.assertEqual("DISABLED_FOR_GROWTH_1_500", strategy.account_loss_cap_policy())
        self.assertEqual(1.5, sizing["growthRequiredBalanceMultiplier"])
        self.assertEqual("GROWTH_1_500", sizing["activeProfile"])
        self.assertEqual("growthRequiredBalanceMultiplier", sizing["activeRequiredBalanceMultiplierRule"])

    def test_account_symbol_overrides_are_recorded_in_specification(self):
        strategy = self.strategy()
        bossa_hash = strategy.strategy_specification["specHash"]
        strategy.cfg.trade_symbol = "US100.pro"
        strategy.cfg.signal_symbol = "US100.pro"

        specification = strategy.build_strategy_specification()

        self.assertEqual("US100.pro", specification["document"]["instruments"]["execution"])
        self.assertEqual("US100.pro", specification["document"]["instruments"]["signal"])
        self.assertNotEqual(bossa_hash, specification["specHash"])

    def test_market_order_priority_delay_is_effective_and_audited(self):
        strategy = self.strategy()
        strategy.cfg.market_order_priority_delay_seconds = 0.5
        strategy.cfg.tsl1pre_market_exit_delay_seconds = 60.0
        strategy.log = Mock()

        with patch("mt5.oppw_core.broker_execution.time_module.sleep") as sleep:
            strategy.wait_for_market_order_priority("BUY")

        sleep.assert_called_once_with(0.5)
        specification = strategy.build_strategy_specification()
        self.assertEqual(
            0.5,
            specification["document"]["calendarAndTime"]["marketOrderPriorityDelaySeconds"],
        )
        self.assertEqual(
            60.0,
            specification["document"]["calendarAndTime"]["tsl1preMarketExitDelaySeconds"],
        )

    def test_required_balance_override_changes_maximum_effective_exposure(self):
        strategy = self.strategy()
        strategy.cfg.required_balance_multiplier = 1.5
        info = SimpleNamespace(volume_min=0.1, volume_step=0.1, volume_max=2.0)

        with patch.object(
            MODULE.mt5,
            "order_calc_margin",
            create=True,
            side_effect=lambda _side, _symbol, volume, _price: float(volume) * 100.0,
        ):
            sizing = strategy.required_balance_sizing(150.0, 150.0, info, 20_000.0, 8)
        effective_leverage = sizing["requiredDeposit"] * strategy.cfg.sizing_multiplier / 150.0

        self.assertEqual(1.0, sizing["volume"])
        self.assertEqual(100.0, sizing["requiredDeposit"])
        self.assertEqual(150.0, sizing["requiredBalance"])
        self.assertEqual(1.5, sizing["requiredBalanceMultiplier"])
        self.assertAlmostEqual(20.0 / 1.5, effective_leverage)
        self.assertEqual(2000.0, strategy.position_notional(sizing["requiredDeposit"]))

    def test_decision_is_immutably_linked_to_specification(self):
        strategy = self.strategy()
        preview = {
            "available": False, "symbol": "US100", "side": "BUY", "strategyLeverage": 8,
            "previousFullWeekChange": 0.0, "previousTradeChange": 0.0,
            "previousFullWeekSource": "test", "previousTradeSource": "test",
            "volume": 0.0, "balance": 0.0, "sizingFreeMargin": 0.0,
            "sizingUnits": 0, "minimumVolumeFloor": False, "error": "test unavailable",
        }
        decision = strategy.strategy_decision_payload(preview)
        self.assertEqual(decision["strategySpecId"], strategy.strategy_specification["specId"])
        self.assertEqual(decision["strategySpecHash"], strategy.strategy_specification["specHash"])

    def test_recorder_emits_a_new_decision_when_specification_changes(self):
        strategy = self.strategy()
        strategy.is_weekend = lambda _now: False
        strategy.is_executor = False
        strategy.log = Mock()
        strategy.last_strategy_decision_signature = None
        strategy.last_strategy_decision_payload = None
        preview = {
            "available": False, "symbol": "US100", "side": "BUY", "strategyLeverage": 8,
            "previousFullWeekChange": 0.0, "previousTradeChange": 0.0,
            "previousFullWeekSource": "test", "previousTradeSource": "test",
            "volume": 0.0, "balance": 0.0, "sizingFreeMargin": 0.0,
            "sizingUnits": 0, "minimumVolumeFloor": False, "error": "test unavailable",
        }

        first = strategy.record_strategy_decision_if_changed(preview=preview)
        strategy.strategy_specification = {
            **strategy.strategy_specification,
            "specId": "c" * 32,
            "specHash": "d" * 64,
        }
        second = strategy.record_strategy_decision_if_changed(preview=preview)

        self.assertNotEqual(first["decisionId"], second["decisionId"])
        self.assertEqual("d" * 64, second["strategySpecHash"])

    def test_next_entry_decision_does_not_replace_active_execution_link(self):
        strategy = self.strategy()
        strategy.is_weekend = lambda _now: False
        strategy.is_executor = True
        strategy.log = Mock()
        strategy.last_strategy_decision_signature = None
        strategy.last_strategy_decision_payload = None
        strategy.state.active_execution_id = "execution-in-progress"
        strategy.state.active_decision_id = "a" * 32
        strategy.state.active_strategy_spec_id = "b" * 32
        strategy.state.active_strategy_spec_hash = "c" * 64
        strategy.state.save = Mock()
        preview = {
            "available": False, "symbol": "US100", "side": "BUY", "strategyLeverage": 8,
            "previousFullWeekChange": 0.0, "previousTradeChange": 0.0,
            "previousFullWeekSource": "test", "previousTradeSource": "test",
            "volume": 0.0, "balance": 0.0, "sizingFreeMargin": 0.0,
            "sizingUnits": 0, "minimumVolumeFloor": False, "error": "test unavailable",
        }

        next_decision = strategy.record_strategy_decision_if_changed(preview=preview)

        self.assertNotEqual("a" * 32, next_decision["decisionId"])
        self.assertEqual("a" * 32, strategy.state.active_decision_id)
        self.assertEqual("b" * 32, strategy.state.active_strategy_spec_id)
        self.assertEqual("c" * 64, strategy.state.active_strategy_spec_hash)
        strategy.state.save.assert_not_called()

    def test_new_execution_binds_to_latest_authoritative_decision(self):
        strategy = self.strategy()
        strategy.state.active_decision_id = "stale-decision"
        strategy.last_strategy_decision_payload = {"decisionId": "d" * 32}

        decision_id = strategy.bind_execution_to_latest_decision()

        self.assertEqual("d" * 32, decision_id)
        self.assertEqual("d" * 32, strategy.state.active_decision_id)
        self.assertEqual(strategy.strategy_specification["specId"], strategy.state.active_strategy_spec_id)
        self.assertEqual(strategy.strategy_specification["specHash"], strategy.state.active_strategy_spec_hash)

    def test_publisher_recalculates_decision_while_flat(self):
        strategy = object.__new__(MODULE.OPPWContinuousStrategy)
        strategy.tz = WARSAW
        strategy.is_weekend = lambda _now: False
        strategy.coordinator = SimpleNamespace(require_role_lease=Mock())
        strategy.reload_state_read_only = Mock()
        strategy.managed_position = Mock(return_value=None)
        strategy.current_m1_bar = Mock(return_value=None)
        strategy.cfg = SimpleNamespace(trade_symbol="US100")
        strategy.record_strategy_decision_if_changed = Mock()
        strategy.last_minute_status = ""
        strategy.emit_status = Mock()
        strategy.print_instance_banner = Mock()
        strategy.publish_account_change_if_needed = Mock(return_value=False)
        strategy.status_signature = Mock(return_value="unchanged")
        strategy.last_meaningful_signature = "unchanged"
        strategy.publish_mobile_minute_status = Mock(return_value=True)
        strategy.publish_mobile_if_due = Mock()

        strategy.publisher_cycle()

        strategy.record_strategy_decision_if_changed.assert_called_once_with()

    def test_publisher_startup_forces_authoritative_trade_read_before_decision(self):
        strategy = object.__new__(MODULE.OPPWContinuousStrategy)
        strategy.monitor_publisher = SimpleNamespace(ready=True, start=Mock())
        strategy.coordinator = SimpleNamespace(require_role_lease=Mock())
        strategy.reload_state_read_only = Mock()
        strategy.tz = WARSAW
        strategy.cfg = SimpleNamespace(trade_symbol="US100")
        strategy.managed_position = Mock(return_value=None)
        strategy.current_m1_bar = Mock(return_value=None)
        strategy.account_funding_signature = Mock(return_value="funding")
        strategy.emit_status = Mock()
        strategy.print_instance_banner = Mock()
        strategy.status_signature = Mock(return_value="status")
        strategy.latest_closed_trade_record = Mock()
        strategy.record_strategy_decision_if_changed = Mock()
        strategy.publish_mobile_minute_status = Mock()
        sys.modules["MetaTrader5"].account_info = Mock(return_value=SimpleNamespace())

        strategy.publisher_startup()

        strategy.monitor_publisher.start.assert_called_once_with()
        strategy.latest_closed_trade_record.assert_called_once_with(force=True)
        strategy.record_strategy_decision_if_changed.assert_called_once_with(force=True)

    def test_execution_stage_contains_spec_and_authority_fields(self):
        strategy = self.strategy()
        messages: list[str] = []
        strategy.log = SimpleNamespace(log=lambda _level, message: messages.append(message))
        strategy.state.active_execution_id = "execution-1"
        strategy.state.active_decision_id = "a" * 32
        strategy.state.active_strategy_spec_id = strategy.strategy_specification["specId"]
        strategy.state.active_strategy_spec_hash = strategy.strategy_specification["specHash"]
        strategy.execution_stage(
            "FILLED", actual_price=29000.0, order_ticket=11, deal_ticket=22,
            side="BUY", volume=0.02, retcode=10009,
        )
        self.assertEqual(len(messages), 1)
        self.assertIn("strategy_spec_id=", messages[0])
        self.assertIn("order_ticket=11", messages[0])
        self.assertIn("deal_ticket=22", messages[0])
        self.assertIn("volume=0.02000000", messages[0])


class BackendAuthorityStaticTests(unittest.TestCase):
    def test_migration_defines_all_authority_tables_and_immutability(self):
        root = Path(__file__).resolve().parents[2]
        migration = (root / "Mobile/backend/sql/migrate_v51_strategy_authority.sql").read_text(encoding="utf-8")
        for table in (
            "strategy_specifications", "strategy_execution_stages", "strategy_fills",
            "strategy_protection_changes", "strategy_trade_ledger",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", migration)
            self.assertIn(f"{table}_no_update", migration)
        self.assertIn("account_cash_flows_no_update", migration)
        self.assertIn("strategy_decisions_no_update", migration)

    def test_both_ingest_paths_write_authority_records(self):
        root = Path(__file__).resolve().parents[2]
        for relative in ("Mobile/backend/ingest.php", "Mobile/backend/events-ingest.php"):
            source = (root / relative).read_text(encoding="utf-8")
            self.assertIn("authority.php", source)
            self.assertIn("oppw_authority_event", source)

    def test_lifecycle_link_repair_is_forward_only_and_registered(self):
        root = Path(__file__).resolve().parents[2]
        order = (root / "Mobile/backend/sql/migration-order.txt").read_text(encoding="utf-8")
        migration_name = "migrate_v56_2_execution_lifecycle_links.sql"
        migration = (root / "Mobile/backend/sql" / migration_name).read_text(encoding="utf-8")

        self.assertEqual(1, order.splitlines().count(migration_name))
        self.assertIn("stage = 'POSITION_VISIBLE'", migration)
        self.assertIn("ROW_NUMBER() OVER", migration)
        self.assertIn("UPDATE strategy_trades", migration)
        self.assertIn("BINARY trade.decision_id <> BINARY lifecycle.decision_id", migration)
        self.assertNotIn("UPDATE strategy_execution_stages", migration)

    def test_trade_linking_prefers_execution_decision_and_is_write_once(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "Mobile/backend/ingest.php").read_text(encoding="utf-8")

        self.assertIn("($execution['decisionId'] ?? null) ?: ($decision['decisionId'] ?? '')", source)
        self.assertIn("decision_id=COALESCE(NULLIF(decision_id,\\'\\'),?)", source)

    def test_manual_trade_import_also_writes_immutable_ledgers(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "Mobile/backend/trade-admin.php").read_text(encoding="utf-8")
        self.assertIn("oppw_store_trade_transition", source)
        self.assertIn("MANUAL_HISTORY_IMPORT", source)
        self.assertIn("INSERT IGNORE INTO strategy_fills", source)


if __name__ == "__main__":
    unittest.main()
