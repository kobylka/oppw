"""Daily-OHLC OPPW research runner with last-two arithmetic control."""

from oppw import run_backtest


if __name__ == "__main__":
    run_backtest(loss_control_lookback=2)
