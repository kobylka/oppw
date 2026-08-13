from __future__ import annotations

import sys
import types
import unittest


sys.modules.setdefault("MetaTrader5", types.ModuleType("MetaTrader5"))

from mt5.oppw_core.monitoring import format_lot_volume


class MonitoringVolumeFormatTests(unittest.TestCase):
    def test_preserves_broker_sub_centilot_precision(self):
        self.assertEqual("0.296", format_lot_volume(0.296))
        self.assertEqual("0.001", format_lot_volume(0.001))

    def test_removes_insignificant_trailing_zeroes(self):
        self.assertEqual("0.3", format_lot_volume(0.30000000))
        self.assertEqual("1", format_lot_volume(1.0))


if __name__ == "__main__":
    unittest.main()
