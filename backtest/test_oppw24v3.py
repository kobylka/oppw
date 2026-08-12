import sys
import types
import unittest


# The focused stop-fill tests do not exercise plotting or return statistics.
# Keep them runnable in the minimal repository-validation Python environment.
sys.modules.setdefault("matplotlib", types.ModuleType("matplotlib"))
sys.modules.setdefault("matplotlib.pyplot", types.ModuleType("matplotlib.pyplot"))
sys.modules.setdefault("numpy", types.ModuleType("numpy"))

from oppw24v3 import (
    failed_recovery_breached,
    failed_recovery_close_decision,
    validate_failed_recovery_distances,
)


class FailedRecoveryExitTests(unittest.TestCase):
    def test_breach_arms_only_after_threshold_crossing(self):
        self.assertFalse(failed_recovery_breached(100.0, 95.71, 0.043))
        self.assertTrue(failed_recovery_breached(100.0, 95.70, 0.043))

    def test_armed_trade_exits_when_close_does_not_reclaim(self):
        self.assertTrue(failed_recovery_close_decision(100.0, 95.99, True, 0.04))

    def test_armed_trade_survives_when_close_reclaims(self):
        self.assertFalse(failed_recovery_close_decision(100.0, 96.0, True, 0.04))

    def test_unarmed_trade_never_uses_recovery_exit(self):
        self.assertFalse(failed_recovery_close_decision(100.0, 90.0, False, 0.04))

    def test_none_disables_breach(self):
        self.assertFalse(failed_recovery_breached(100.0, 90.0, None))

    def test_rejects_inverted_distances(self):
        with self.assertRaises(ValueError):
            validate_failed_recovery_distances(0.04, 0.043)


if __name__ == "__main__":
    unittest.main()
