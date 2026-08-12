"""OPPW24 two-outcome loss gate plus the premarket-low entry gate."""

import argparse

from oppw24 import run_backtest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--leverage_override",
        action="store_true",
        help="Use the fixed 1.765 sizing divisor instead of 20 / LEVERAGE.",
    )
    args = parser.parse_args()
    run_backtest(
        loss_control_lookback=2,
        premarket_low_enabled=True,
        leverage_override=args.leverage_override,
    )
