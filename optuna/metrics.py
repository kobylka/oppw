from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import numpy as np


def sharpe_ratio(
    returns: Iterable[float],
    periods_per_year: float = 52.0,
) -> float:
    values = np.asarray(list(returns), dtype=float)

    if len(values) < 2:
        return float("nan")

    deviation = np.std(values, ddof=1)

    if deviation == 0:
        return float("nan")

    return float(
        np.mean(values) / deviation * np.sqrt(periods_per_year)
    )


def sortino_ratio(
    returns: Iterable[float],
    periods_per_year: float = 52.0,
    target_return: float = 0.0,
) -> float:
    values = np.asarray(list(returns), dtype=float)

    if len(values) == 0:
        return float("nan")

    downside = np.minimum(0.0, values - target_return)
    downside_deviation = np.sqrt(np.mean(downside**2))

    if downside_deviation == 0:
        return float("nan")

    return float(
        np.mean(values - target_return)
        / downside_deviation
        * np.sqrt(periods_per_year)
    )


def max_drawdown(equity: Iterable[float]) -> float:
    values = np.asarray(list(equity), dtype=float)

    if len(values) == 0:
        return 0.0

    peaks = np.maximum.accumulate(values)
    drawdowns = values / peaks - 1.0

    return float(np.min(drawdowns))


def build_backtest_result(
    *,
    initial_balance: float,
    final_balance: float,
    deposited: float,
    daily_equity_points: list[tuple[str, float]],
    trade_returns: list[float],
    days_in_position: int,
    start_date: str,
    end_date: str,
) -> dict:
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")

    if end <= start:
        raise ValueError("end_date must be later than start_date")

    points = sorted(
        (
            datetime.strptime(date, "%Y%m%d"),
            float(equity),
        )
        for date, equity in daily_equity_points
    )

    equity_values = [initial_balance]
    equity_values.extend(equity for _, equity in points)

    period_days = (end - start).days
    period_years = period_days / 365.25

    if initial_balance <= 0 or final_balance <= 0:
        full_period_cagr = -1.0
    else:
        full_period_cagr = (
            final_balance / initial_balance
        ) ** (1.0 / period_years) - 1.0

    final_year = (end - timedelta(days=1)).year

    year_end_equity: dict[int, float] = {}

    for date, equity in points:
        year_end_equity[date.year] = equity

    yearly_returns: dict[str, float] = {}
    previous_equity = initial_balance

    for year in range(start.year, final_year + 1):
        ending_equity = year_end_equity.get(
            year,
            previous_equity,
        )

        if previous_equity <= 0:
            year_return = -1.0
        else:
            year_return = ending_equity / previous_equity - 1.0

        yearly_returns[str(year)] = float(year_return)
        previous_equity = ending_equity

    return {
        "start_date": start_date,
        "end_date": end_date,
        "initial_balance": float(initial_balance),
        "final_balance": float(final_balance),
        "deposited": int(deposited),
        "full_period_cagr": float(full_period_cagr),
        "yearly_returns": yearly_returns,
        "max_drawdown": max_drawdown(equity_values),
        "sharpe": sharpe_ratio(trade_returns),
        "sortino": sortino_ratio(trade_returns),
        "mean_trade": (
            float(np.mean(trade_returns))
            if trade_returns
            else float("nan")
        ),
        "median_trade": (
            float(np.median(trade_returns))
            if trade_returns
            else float("nan")
        ),
        "trade_count": len(trade_returns),
        "final_balance": final_balance,
        "final_cagr": round(final_balance / deposited, 2),
        "days_in_position": days_in_position
    }