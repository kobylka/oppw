from __future__ import annotations

import importlib.util
import logging
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo


def load_strategy_module():
    sys.modules.setdefault("exchange_calendars", types.ModuleType("exchange_calendars"))
    sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))
    source = Path(__file__).resolve().parents[1] / "oppw_mt5_continuous.py"
    spec = importlib.util.spec_from_file_location("oppw_publisher_worker_recovery_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_strategy_module()


class FakeCoordinator:
    def __init__(self, valid: bool):
        self.valid = valid
        self.invalid_observed = threading.Event()
        self.owner_id = "publisher-worker-test"
        self.fencing_token = 17

    def role_lease_valid(self) -> bool:
        if not self.valid:
            self.invalid_observed.set()
        return self.valid

    def dedicated_publisher_active(self) -> bool:
        return self.valid

    def actor_payload(self) -> dict[str, object]:
        if not self.valid:
            raise AssertionError("publishing attempted without a valid lease")
        return {
            "role": "PUBLISHER",
            "ownerId": self.owner_id,
            "fencingToken": self.fencing_token,
        }


class PublisherWorkerRecoveryTests(unittest.TestCase):
    def publisher(self, directory: str, coordinator: FakeCoordinator):
        cfg = SimpleNamespace(
            monitor_enabled=True,
            monitor_ingest_url="https://example.invalid/ingest.php",
            events_ingest_url="https://example.invalid/events-ingest.php",
            monitor_write_token="test-token",
            monitor_account_key="REAL",
            monitor_minute_snapshot_buffer_size=8,
            monitor_event_buffer_size=32,
            monitor_history_file=Path(directory) / "equity.json",
            monitor_equity_history_points=32,
            monitor_equity_sample_seconds=60.0,
            monitor_publish_interval_seconds=5.0,
            monitor_timeout_seconds=0.1,
            monitor_error_log_interval_seconds=0.1,
        )
        logger = logging.getLogger(f"publisher-worker-test-{id(coordinator)}")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        return MODULE.MobileMonitorPublisher(
            cfg,
            logger,
            ZoneInfo("UTC"),
            MODULE.INSTANCE_MODE_PUBLISHER,
            coordinator,
        )

    def test_worker_pauses_fail_closed_and_resumes_after_lease_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            coordinator = FakeCoordinator(valid=False)
            publisher = self.publisher(directory, coordinator)
            delivered: list[tuple[dict[str, object], list[dict[str, object]]]] = []
            delivered_event = threading.Event()

            def send(snapshot, events):
                if not coordinator.valid:
                    raise AssertionError("snapshot sent while lease was invalid")
                delivered.append((snapshot, events))
                delivered_event.set()

            publisher.send = send
            publisher.start()
            self.addCleanup(publisher.stop)
            publisher.submit_snapshot({"statusUpdate": {"kind": "MINUTE"}}, guaranteed=True)

            self.assertTrue(coordinator.invalid_observed.wait(1.0))
            self.assertIsNotNone(publisher.thread)
            self.assertTrue(publisher.thread.is_alive())
            self.assertEqual([], delivered)

            coordinator.valid = True
            with publisher.condition:
                publisher.condition.notify_all()

            self.assertTrue(delivered_event.wait(1.0))
            self.assertEqual(1, len(delivered))
            self.assertEqual("MINUTE", delivered[0][0]["statusUpdate"]["kind"])

    def test_start_replaces_a_dead_worker_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            coordinator = FakeCoordinator(valid=True)
            publisher = self.publisher(directory, coordinator)
            dead_thread = threading.Thread(target=lambda: None)
            dead_thread.start()
            dead_thread.join()
            publisher.thread = dead_thread

            publisher.start()
            self.addCleanup(publisher.stop)

            self.assertIsNot(dead_thread, publisher.thread)
            self.assertIsNotNone(publisher.thread)
            self.assertTrue(publisher.thread.is_alive())

    def test_shutdown_during_lease_pause_is_prompt_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            coordinator = FakeCoordinator(valid=False)
            publisher = self.publisher(directory, coordinator)
            delivered: list[object] = []
            publisher.send = lambda snapshot, events: delivered.append((snapshot, events))
            publisher.start()
            worker = publisher.thread
            publisher.submit_snapshot({"statusUpdate": {"kind": "MINUTE"}}, guaranteed=True)
            self.assertTrue(coordinator.invalid_observed.wait(1.0))

            started = time.monotonic()
            publisher.stop()

            self.assertLess(time.monotonic() - started, 1.0)
            self.assertIsNotNone(worker)
            self.assertFalse(worker.is_alive())
            self.assertEqual([], delivered)


if __name__ == "__main__":
    unittest.main()
