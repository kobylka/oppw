import inspect
import sys
import types
import unittest
from pathlib import Path


sys.modules.setdefault("matplotlib", types.ModuleType("matplotlib"))
sys.modules.setdefault("matplotlib.pyplot", types.ModuleType("matplotlib.pyplot"))
if "numpy" in sys.modules and not hasattr(sys.modules["numpy"], "asarray"):
    del sys.modules["numpy"]
import numpy  # noqa: F401 - ensure classifier tests use the real dependency

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


def load_oppw24_module():
    source = Path(__file__).with_name("oppw24.py")
    namespace = {"__name__": "oppw24_cli_test", "__file__": str(source)}
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), namespace)
    return namespace


class RemovedRollingCandleExitTests(unittest.TestCase):
    def test_rolling_candle_exit_is_not_exposed_by_oppw24(self):
        module = load_oppw24_module()
        parameters = inspect.signature(module["Sim"].process).parameters

        self.assertNotIn("rolling_candle_exit_signal", module)
        self.assertNotIn("early_exit_rule", parameters)
        self.assertNotIn("early_exit_require_all", parameters)


class StructuralBreakdownExitTests(unittest.TestCase):
    def test_requires_entry_loss_opening_range_break_and_persistence(self):
        helper = load_oppw24_module()["structural_breakdown_exit_signal"]
        quotes = [[0.0, 0.0, 0.0, 0.0] for _ in range(934)] + [
            [100.0, 100.2, 99.8, 100.0],
            [100.0, 100.1, 99.7, 99.9],
            [99.9, 100.0, 98.7, 99.0],
            [99.0, 99.1, 98.5, 98.8],
        ]
        rule = {
            "opening_range_minutes": 2,
            "entry_loss": 0.01,
            "persistence": 2,
        }

        self.assertFalse(helper(quotes, 936, 934, 100.0, rule))
        self.assertTrue(helper(quotes, 937, 934, 100.0, rule))

    def test_rule_list_uses_logical_or(self):
        helper = load_oppw24_module()["structural_breakdown_exit_signal"]
        quotes = [[0.0, 0.0, 0.0, 0.0] for _ in range(934)] + [
            [100.0, 100.1, 99.8, 100.0],
            [100.0, 100.0, 99.7, 99.9],
            [99.9, 100.0, 98.5, 98.8],
        ]
        matching = {
            "opening_range_minutes": 2,
            "entry_loss": 0.01,
            "persistence": 1,
        }
        nonmatching = {
            "opening_range_minutes": 2,
            "entry_loss": 0.05,
            "persistence": 1,
        }

        self.assertTrue(
            helper(quotes, 936, 934, 100.0, (nonmatching, matching))
        )

    def test_first_day_slow_window_can_include_same_day_premarket(self):
        helper = load_oppw24_module()["structural_breakdown_exit_signal"]
        quotes = [[100.0, 100.0, 100.0, 100.0] for _ in range(934)] + [
            [100.0, 100.0, 99.8, 100.0],
            [100.0, 100.0, 99.7, 99.9],
            [99.9, 100.0, 98.0, 98.5],
        ]
        base_rule = {
            "opening_range_minutes": 2,
            "entry_loss": 0.01,
            "persistence": 1,
            "slow_minutes": 60,
            "slow_decline": 0.015,
        }

        self.assertFalse(helper(quotes, 936, 934, 100.0, base_rule, True))
        premarket_rule = dict(
            base_rule,
            first_day_slow_window_includes_premarket=True,
        )
        self.assertTrue(helper(quotes, 936, 934, 100.0, premarket_rule, True))
        self.assertFalse(helper(quotes, 936, 934, 100.0, premarket_rule, False))


class BroadExitTests(unittest.TestCase):
    def test_profit_giveback_requires_prior_profit_and_retracement(self):
        helper = load_oppw24_module()["broad_exit_signal"]
        quotes = [[0.0, 0.0, 0.0, 0.0] for _ in range(934)] + [
            [100.0, 102.0, 99.8, 100.5],
        ]
        rule = {"family": "profit_giveback", "activation": 0.015, "giveback": 0.01}

        self.assertTrue(
            helper(quotes, 934, 934, 100.0, "20200106", "20200106", 102.0, rule)
        )

    def test_intraday_time_stop_only_fires_at_checkpoint(self):
        helper = load_oppw24_module()["broad_exit_signal"]
        quotes = [[0.0, 0.0, 0.0, 0.0] for _ in range(994)] + [
            [99.0, 99.1, 98.9, 99.0],
        ]
        rule = {"family": "intraday_time_stop", "minutes": 60, "minimum_return": -0.005}

        self.assertTrue(
            helper(quotes, 994, 934, 100.0, "20200106", "20200106", 100.0, rule)
        )


class MarketStructureExitTests(unittest.TestCase):
    def test_lower_close_sequence_requires_monotonic_closes(self):
        helper = load_oppw24_module()["market_structure_exit_signal"]
        quotes = [[0.0, 0.0, 0.0, 0.0] for _ in range(934)] + [
            [100.0, 100.0, 99.8, 100.0],
            [99.9, 100.0, 99.4, 99.5],
            [99.4, 99.5, 98.8, 99.0],
        ]
        rule = {"family": "lower_close_sequence", "count": 2, "minimum_decline": 0.009}

        self.assertTrue(helper(quotes, 936, 934, 100.0, 98.0, 4.0, rule))

    def test_previous_low_break_requires_persistent_closes(self):
        helper = load_oppw24_module()["market_structure_exit_signal"]
        quotes = [[0.0, 0.0, 0.0, 0.0] for _ in range(934)] + [
            [100.0, 100.0, 98.8, 98.9],
            [98.9, 99.0, 98.6, 98.8],
        ]
        rule = {"family": "previous_low_break", "buffer": 0.01, "persistence": 2}

        self.assertTrue(helper(quotes, 935, 934, 100.0, 100.0, 4.0, rule))


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


class Oppw24CommandLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_oppw24_module()

    def test_each_loss_protection_is_independently_selectable(self):
        parser = self.module["build_parser"]()
        options_for = self.module["loss_protection_options"]
        cases = {
            "--arithmetic-last-two": "arithmetic_loss_control_enabled",
            "--gap-momentum": "gap_momentum_enabled",
            "--tuesday-normalization": "tuesday_normalization_enabled",
            "--premarket-low": "premarket_low_enabled",
        }
        for argument, selected in cases.items():
            options = options_for(parser.parse_args([argument]))
            self.assertTrue(options[selected], argument)
            self.assertEqual(
                2 if selected == "arithmetic_loss_control_enabled" else None,
                options["loss_control_lookback"],
                argument,
            )

    def test_all_protections_enables_every_protection(self):
        parser = self.module["build_parser"]()
        options = self.module["loss_protection_options"](
            parser.parse_args(["--all-protections"])
        )
        self.assertEqual(2, options["loss_control_lookback"])
        self.assertTrue(all(value for key, value in options.items() if key != "loss_control_lookback"))

    def test_singular_all_protection_alias_matches_plural(self):
        parser = self.module["build_parser"]()
        options_for = self.module["loss_protection_options"]
        self.assertEqual(
            options_for(parser.parse_args(["--all-protections"])),
            options_for(parser.parse_args(["--all-protection"])),
        )

    def test_or5_exit_is_opt_in(self):
        parser = self.module["build_parser"]()

        self.assertFalse(parser.parse_args([]).or5_exit)
        self.assertTrue(parser.parse_args(["--or5-exit"]).or5_exit)
        self.assertIn("--or5-exit", parser.format_help())

    def test_or5_exit_rule_matches_tested_60_minute_variant(self):
        self.assertEqual(
            {
                "opening_range_minutes": 5,
                "entry_loss": 0.005,
                "persistence": 1,
                "slow_minutes": 60,
                "slow_decline": 0.015,
            },
            self.module["OR5_EXIT_RULE"],
        )
        selected_rule = self.module["selected_structural_exit_rule"]
        self.assertIsNone(selected_rule(False))
        self.assertEqual(self.module["OR5_EXIT_RULE"], selected_rule(True))
        self.assertIsNot(self.module["OR5_EXIT_RULE"], selected_rule(True))

    def test_meta_filter_is_opt_in(self):
        parser = self.module["build_parser"]()

        self.assertFalse(parser.parse_args([]).meta_filter)
        self.assertTrue(parser.parse_args(["--meta-filter"]).meta_filter)
        self.assertIn("--meta-filter", parser.format_help())


class MetaFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_oppw24_module()

    def test_classifier_is_unavailable_during_warmup(self):
        fit = self.module["fit_meta_filter"]
        self.assertIsNone(fit([[0.0]] * 39, [0.0] * 39))

    def test_classifier_assigns_higher_risk_to_worst_pattern(self):
        fit = self.module["fit_meta_filter"]
        probability = self.module["meta_filter_worst_probability"]
        features = [[-2.0 + index * 0.01] for index in range(5)] + [
            [1.0 + index * 0.01] for index in range(45)
        ]
        outcomes = [-0.05] * 5 + [0.01] * 45

        model = fit(features, outcomes)

        self.assertIsNotNone(model)
        self.assertGreater(probability(model, [-2.0]), probability(model, [1.0]))


if __name__ == "__main__":
    unittest.main()
