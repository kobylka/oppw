"""OPPW24 three-outcome loss gate plus the premarket-low entry gate."""

from oppw24 import run_backtest


if __name__ == "__main__":
    run_backtest(loss_control_lookback=3, premarket_low_enabled=True)
