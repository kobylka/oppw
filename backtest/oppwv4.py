"""Daily-OHLC OPPW research runner with last-three arithmetic control."""

from oppw import run_backtest


if __name__ == "__main__":
    run_backtest(loss_control_lookback=3)
