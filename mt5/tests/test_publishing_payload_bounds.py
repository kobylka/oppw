from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from mt5.oppw_core.publishing import (
    SNAPSHOT_EQUITY_HISTORY_FALLBACK_POINTS,
    MobileMonitorPublisher,
)


class PublishingPayloadBoundsTests(unittest.TestCase):
    def test_full_local_history_is_bounded_in_snapshot_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            publisher = object.__new__(MobileMonitorPublisher)
            publisher.cfg = SimpleNamespace(
                monitor_history_file=Path(directory) / "equity.json",
                monitor_equity_history_points=10080,
                monitor_equity_sample_seconds=60.0,
            )
            start = datetime(2026, 8, 6, tzinfo=UTC)
            persisted_history = [
                {
                    "time": (start + timedelta(minutes=index)).isoformat(),
                    "value": 10000.0 + index,
                }
                for index in range(10079)
            ]
            publisher.cfg.monitor_history_file.write_text(
                json.dumps(persisted_history), encoding="utf-8"
            )
            publisher.equity_history = []
            snapshot = {"account": {"equity": 25000.0}}

            publisher.update_equity_history(
                snapshot, (start + timedelta(minutes=10079)).isoformat()
            )

            self.assertEqual(10080, len(publisher.equity_history))
            self.assertEqual(
                SNAPSHOT_EQUITY_HISTORY_FALLBACK_POINTS,
                len(snapshot["equityHistory"]),
            )
            self.assertLess(len(json.dumps(snapshot).encode("utf-8")), 65536)


if __name__ == "__main__":
    unittest.main()
