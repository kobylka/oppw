from __future__ import annotations

import importlib.util
import sys
import time
import types
import unittest
from datetime import date, datetime, time as datetime_time
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
    spec = importlib.util.spec_from_file_location("oppw_v48_5_lease_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()


def config():
    return SimpleNamespace(
        monitor_account_key="DEMO",
        monitor_write_token="test",
        coordination_url="https://example.invalid/coordination.php",
        coordination_timeout_seconds=0.05,
        role_lease_ttl_seconds=1.0,
        role_lease_heartbeat_seconds=0.25,
        role_lease_safety_margin_seconds=0.10,
    )


class LeaseRecoveryTests(unittest.TestCase):
    def test_transport_failure_is_retried_before_cached_lease_expires(self):
        coordinator = MODULE.BackendLeaseCoordinator(config(), "EXECUTOR", "DEMO")
        calls = []

        def request(action, **_values):
            calls.append(action)
            if action == "acquireLease":
                return {"ok": True, "acquired": True, "fencingToken": 7, "ttlSeconds": 1.0}
            if calls.count("renewLease") == 1:
                raise MODULE.CoordinationError("simulated timeout")
            return {"ok": True, "renewed": True, "fencingToken": 7, "ttlSeconds": 1.0}

        coordinator._request = request
        coordinator.start()
        time.sleep(0.70)
        self.assertGreaterEqual(calls.count("renewLease"), 2)
        self.assertTrue(coordinator.role_lease_valid())
        coordinator.stop()

    def test_explicit_fencing_rejection_is_immediate(self):
        coordinator = MODULE.BackendLeaseCoordinator(config(), "EXECUTOR", "DEMO")

        def request(action, **_values):
            if action == "acquireLease":
                return {"ok": True, "acquired": True, "fencingToken": 4, "ttlSeconds": 1.0}
            if action == "renewLease":
                return {"ok": True, "renewed": False, "fencingToken": 4, "ttlSeconds": 1.0}
            return {"ok": True}

        coordinator._request = request
        coordinator.start()
        time.sleep(0.40)
        self.assertTrue(coordinator.lease_lost_event.is_set())
        self.assertFalse(coordinator.role_lease_valid())
        coordinator.stop()

    def test_suspended_process_can_reacquire_with_new_fencing_token(self):
        coordinator = MODULE.BackendLeaseCoordinator(config(), "EXECUTOR", "DEMO")
        coordinator.fencing_token = 10
        coordinator.lease_lost_event.set()
        coordinator.thread = None

        def request(action, **_values):
            self.assertEqual(action, "acquireLease")
            return {"ok": True, "acquired": True, "fencingToken": 11, "ttlSeconds": 1.0}

        coordinator._request = request
        self.assertTrue(coordinator.recover_role_lease(0.01))
        self.assertEqual(coordinator.fencing_token, 11)
        self.assertTrue(coordinator.role_lease_valid())
        coordinator.stop_event.set()


class BreakEvenScheduleTests(unittest.TestCase):
    def strategy(self, *, armed=False, last_processed="", last_action=""):
        warsaw = ZoneInfo("Europe/Warsaw")
        state = SimpleNamespace(
            entry_price=29_000.0,
            entry_signal_daily_open=29_100.0,
            entry_signal_open_pending=False,
            break_even=armed,
            open_date="2026-07-20",
            last_close_processed_date=last_processed,
            last_close_action_date=last_action,
        )
        strategy = SimpleNamespace(
            state=state,
            cfg=SimpleNamespace(break_even_ratio=0.996),
            final_trading_day=lambda _opened: date(2026, 7, 24),
            is_trading_session_day=lambda day: day.weekday() < 5,
            session_times=lambda day: SimpleNamespace(
                close_processing=datetime.combine(day, datetime_time(22, 1), warsaw),
                weekly_close=datetime.combine(day, datetime_time(21, 59, 57), warsaw),
            ),
            mt5_timestamp_to_local=lambda value: datetime.fromtimestamp(value, warsaw),
        )
        return strategy

    def test_first_check_is_next_trading_day_close(self):
        strategy = self.strategy()
        position = SimpleNamespace(price_open=29_000.0, time=0)
        now = datetime(2026, 7, 20, 16, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
        result = MODULE.OPPWContinuousStrategy.break_even_check_payload(strategy, position, now)
        self.assertEqual(result["status"], "SCHEDULED")
        self.assertEqual(result["nextCheckAt"], "2026-07-21T21:59:57+02:00")
        self.assertAlmostEqual(result["threshold"], 29_100.0 * 0.996)

    def test_processed_close_advances_to_following_session(self):
        strategy = self.strategy(last_processed="2026-07-21")
        position = SimpleNamespace(price_open=29_000.0, time=0)
        now = datetime(2026, 7, 21, 22, 2, tzinfo=ZoneInfo("Europe/Warsaw"))
        result = MODULE.OPPWContinuousStrategy.break_even_check_payload(strategy, position, now)
        self.assertEqual(result["nextCheckAt"], "2026-07-22T21:59:57+02:00")

    def test_completed_post_ch_check_advances_immediately(self):
        strategy = self.strategy(last_action="2026-07-21")
        position = SimpleNamespace(price_open=29_000.0, time=0)
        now = datetime(2026, 7, 21, 21, 59, 58, tzinfo=ZoneInfo("Europe/Warsaw"))
        result = MODULE.OPPWContinuousStrategy.break_even_check_payload(strategy, position, now)
        self.assertEqual(result["status"], "SCHEDULED")
        self.assertEqual(result["nextCheckAt"], "2026-07-22T21:59:57+02:00")

    def test_armed_state_has_no_future_arming_check(self):
        strategy = self.strategy(armed=True)
        position = SimpleNamespace(price_open=29_000.0, time=0)
        now = datetime(2026, 7, 21, 12, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
        result = MODULE.OPPWContinuousStrategy.break_even_check_payload(strategy, position, now)
        self.assertEqual(result["status"], "ARMED")
        self.assertEqual(result["nextCheckAt"], "")


class BreakEvenAfterChTests(unittest.TestCase):
    def strategy(self, signal_price: float, *, final_day=False):
        warsaw = ZoneInfo("Europe/Warsaw")
        state = SimpleNamespace(
            last_close_action_date="",
            entry_signal_daily_open=100.0,
            entry_signal_open_pending=False,
            entry_price=100.0,
            open_date="2026-07-20",
            break_even=False,
            save=lambda _path: None,
        )
        closed = []
        emitted = []
        strategy = SimpleNamespace(
            state=state,
            cfg=SimpleNamespace(
                tpps=(0.007, 0.02, 0.05, 0.05, 0.05),
                break_even_ratio=0.996,
                state_file=Path("unused.json"),
            ),
            session_times=lambda day: SimpleNamespace(
                weekly_close=datetime.combine(day, datetime_time(21, 59, 57), warsaw)
            ),
            final_trading_day=lambda day: day if final_day else date(2026, 7, 24),
            tpp_for_day=lambda _day: 0.02,
            live_signal_price=lambda: signal_price,
            close_position_market=lambda _position, reason, _now: closed.append(reason) or True,
            emit_status=lambda reason, _position, _now: emitted.append(reason),
            log=SimpleNamespace(info=lambda *_args, **_kwargs: None),
        )
        return strategy, state, closed, emitted

    def test_break_even_runs_after_false_ch(self):
        strategy, state, closed, emitted = self.strategy(99.5)
        now = datetime(2026, 7, 21, 21, 59, 57, tzinfo=ZoneInfo("Europe/Warsaw"))
        result = MODULE.OPPWContinuousStrategy.maybe_execute_close_action(strategy, object(), now)
        self.assertFalse(result)
        self.assertEqual(closed, [])
        self.assertTrue(state.break_even)
        self.assertEqual(state.last_close_action_date, "2026-07-21")
        self.assertEqual(emitted, ["BREAK_EVEN_ARMED"])

    def test_ch_has_priority_over_break_even(self):
        strategy, state, closed, emitted = self.strategy(103.0)
        now = datetime(2026, 7, 21, 21, 59, 57, tzinfo=ZoneInfo("Europe/Warsaw"))
        result = MODULE.OPPWContinuousStrategy.maybe_execute_close_action(strategy, object(), now)
        self.assertTrue(result)
        self.assertEqual(closed, ["CH"])
        self.assertFalse(state.break_even)
        self.assertEqual(emitted, [])

    def test_weekly_to_has_priority_over_break_even(self):
        strategy, state, closed, emitted = self.strategy(99.5, final_day=True)
        now = datetime(2026, 7, 24, 21, 59, 57, tzinfo=ZoneInfo("Europe/Warsaw"))
        result = MODULE.OPPWContinuousStrategy.maybe_execute_close_action(strategy, object(), now)
        self.assertTrue(result)
        self.assertEqual(closed, ["TO"])
        self.assertFalse(state.break_even)
        self.assertEqual(emitted, [])


if __name__ == "__main__":
    unittest.main()
