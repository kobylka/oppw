import sys
import types
import unittest


sys.modules.setdefault("matplotlib", types.ModuleType("matplotlib"))
sys.modules.setdefault("matplotlib.pyplot", types.ModuleType("matplotlib.pyplot"))
sys.modules.setdefault("numpy", types.ModuleType("numpy"))

from oppw_loss_control import (
    LOSS_CONTROL_DEFER_TUESDAY,
    LOSS_CONTROL_ENTER,
    LOSS_CONTROL_SKIP_ARITHMETIC,
    LOSS_CONTROL_SKIP_GAP_MOMENTUM,
    LOSS_CONTROL_SKIP_PREMARKET_LOW,
    arithmetic_loss_control_trigger,
    loss_control_entry_decision,
    normalized_tuesday_reentry,
    opening_gap_momentum_trigger,
    premarket_closes_near_low,
)


class ArithmeticLossControlTests(unittest.TestCase):
    def test_last_three_uses_combined_arithmetic_return(self):
        self.assertTrue(
            arithmetic_loss_control_trigger([-0.025, 0.010, -0.006], 3)
        )

    def test_last_two_uses_only_two_latest_outcomes(self):
        outcomes = [-0.050, 0.004, -0.025]
        self.assertTrue(arithmetic_loss_control_trigger(outcomes, 2))
        self.assertTrue(arithmetic_loss_control_trigger(outcomes, 3))

    def test_insufficient_history_does_not_skip(self):
        self.assertFalse(arithmetic_loss_control_trigger([-0.030, 0.005], 3))

    def test_zero_outcome_from_skipped_week_participates(self):
        self.assertTrue(arithmetic_loss_control_trigger([-0.021, 0.0], 2))

    def test_arithmetic_damage_has_priority_over_market_gate(self):
        decision = loss_control_entry_decision(
            [-0.011, -0.010],
            2,
            101.0,
            100.0,
            -0.01,
            True,
            premarket_low=True,
        )
        self.assertEqual(LOSS_CONTROL_SKIP_ARITHMETIC, decision)


class GapMomentumReentryTests(unittest.TestCase):
    def test_gate_uses_cash_open_and_previous_cash_close(self):
        self.assertTrue(opening_gap_momentum_trigger(101.0, 100.0, -0.005))
        self.assertFalse(opening_gap_momentum_trigger(100.99, 100.0, -0.005))
        self.assertFalse(opening_gap_momentum_trigger(101.0, 100.0, -0.0049))

    def test_monday_gate_defers_to_tuesday(self):
        decision = loss_control_entry_decision(
            [0.0, 0.0, 0.0],
            3,
            101.0,
            100.0,
            -0.005,
            True,
        )
        self.assertEqual(LOSS_CONTROL_DEFER_TUESDAY, decision)

    def test_holiday_tuesday_gate_skips_without_another_reentry(self):
        decision = loss_control_entry_decision(
            [0.0, 0.0],
            2,
            101.0,
            100.0,
            -0.005,
            False,
        )
        self.assertEqual(LOSS_CONTROL_SKIP_GAP_MOMENTUM, decision)

    def test_no_trigger_enters_normally(self):
        decision = loss_control_entry_decision(
            [0.0, 0.0],
            2,
            100.5,
            100.0,
            -0.01,
            True,
        )
        self.assertEqual(LOSS_CONTROL_ENTER, decision)


class PremarketLowTests(unittest.TestCase):
    def test_premarket_low_operates_without_arithmetic_lookback(self):
        decision = loss_control_entry_decision(
            [],
            None,
            101.0,
            100.0,
            -0.01,
            True,
            premarket_low=True,
        )
        self.assertEqual(LOSS_CONTROL_SKIP_PREMARKET_LOW, decision)

    def test_disabling_lookback_does_not_enable_gap_momentum_gate(self):
        decision = loss_control_entry_decision(
            [],
            None,
            101.0,
            100.0,
            -0.01,
            True,
            premarket_low=False,
        )
        self.assertEqual(LOSS_CONTROL_ENTER, decision)

    def test_exact_range_and_close_location_boundaries_trigger(self):
        self.assertTrue(
            premarket_closes_near_low(100.0, 100.8, 100.0, 100.12)
        )

    def test_narrow_range_does_not_trigger(self):
        self.assertFalse(
            premarket_closes_near_low(100.0, 100.79, 100.0, 100.0)
        )

    def test_close_above_bottom_fifteen_percent_does_not_trigger(self):
        self.assertFalse(
            premarket_closes_near_low(100.0, 101.0, 100.0, 100.151)
        )

    def test_premarket_low_skips_instead_of_deferring_to_tuesday(self):
        decision = loss_control_entry_decision(
            [0.0, 0.0],
            2,
            101.0,
            100.0,
            -0.01,
            True,
            premarket_low=True,
        )
        self.assertEqual(LOSS_CONTROL_SKIP_PREMARKET_LOW, decision)

    def test_tuesday_normalization_is_symmetric_from_friday(self):
        self.assertTrue(normalized_tuesday_reentry(100.0, 100.5))
        self.assertTrue(normalized_tuesday_reentry(100.0, 99.5))
        self.assertFalse(normalized_tuesday_reentry(100.0, 100.51))
        self.assertFalse(normalized_tuesday_reentry(100.0, 99.49))


if __name__ == "__main__":
    unittest.main()
