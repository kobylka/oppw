from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class MobileEquityBoundaryWiringTests(unittest.TestCase):
    def test_mt5_publishes_manual_position_authority_in_live_and_weekend_snapshots(self):
        for relative in ("mt5/oppw_core/monitoring.py", "mt5/oppw_core/runtime.py"):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn('"manual": self.is_manual_position(position)', source)

    def test_backend_uses_the_canonical_boundary_helper(self):
        status = (ROOT / "Mobile/backend/status.php").read_text(encoding="utf-8")
        helper = (ROOT / "Mobile/backend/equity-periods.php").read_text(encoding="utf-8")
        self.assertIn("equity-periods.php", status)
        self.assertIn("oppw_equity_period_boundaries", status)
        self.assertIn("oppw_first_regular_market_start", status)
        self.assertIn("weekCashOpen", helper)
        self.assertIn("($position['manual'] ?? false) !== true", helper)
        self.assertIn("$opened >= $marketOpen", helper)
        self.assertIn("setTime(15, 30, 0)", helper)
        self.assertIn("? $weeklyStart", helper)

    def test_android_and_contract_parse_the_additive_manual_flag(self):
        models = (ROOT / "Mobile/app/src/main/java/com/oppw/monitor/data/Models.kt").read_text(encoding="utf-8")
        parser = (ROOT / "Mobile/app/src/main/java/com/oppw/monitor/data/JsonParser.kt").read_text(encoding="utf-8")
        fixture = (ROOT / "contracts/fixtures/open-position.json").read_text(encoding="utf-8")
        release = (ROOT / "tools/release.ps1").read_text(encoding="utf-8")
        self.assertIn("val manual: Boolean = false", models)
        self.assertIn('manual = json.optBoolean("manual", false)', parser)
        self.assertIn('"manual": false', fixture)
        self.assertIn("equity-periods-test.php", release)


if __name__ == "__main__":
    unittest.main()
