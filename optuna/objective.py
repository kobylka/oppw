from __future__ import annotations

import numpy as np
import optuna

from backtest_adapter import evaluate_strategy
from config import (
    ENFORCE_NONDECREASING_TARGETS,
    FRIDAY_STOP,
    MAX_TARGET_STEP,
    MAX_TRAIN_DRAWDOWN,
    P1_RANGE,
    P2_RANGE,
    P3_RANGE,
    P4_RANGE,
    P5_RANGE,
    THURSDAY_STOP,
    MINUTE_OPEN,
    MINUTE_CLOSE,
    TRAIN_END_DATE,
    TRAIN_END_YEAR,
    TRAIN_START_DATE,
    TRAIN_START_YEAR,
)
from models import StrategyParams


def valid_parameters(params: StrategyParams) -> bool:
    if params.p2 < params.p1:
        raise optuna.TrialPruned()
    if params.minute_close <= params.minute_open:
        raise optuna.TrialPruned()
    return True


def suggest_parameters(
    trial: optuna.Trial,
) -> StrategyParams:
    params = StrategyParams(
        p1=trial.suggest_int("p1", *P1_RANGE, step=1),
        p2=trial.suggest_int("p2", *P2_RANGE, step=1),
        p3=trial.suggest_int("p3", *P3_RANGE, step=5),
        p4=trial.suggest_int("p4", *P4_RANGE, step=5),
        p5=trial.suggest_int("p5", *P5_RANGE, step=5),
        thursday_stop=trial.suggest_int(
            "thursday_stop",
            *THURSDAY_STOP,
            step =5
        ),
        friday_stop=trial.suggest_int(
            "friday_stop",
            *FRIDAY_STOP,
            step = 5
        ),
        minute_open=trial.suggest_int(
            "minute_open",
            *MINUTE_OPEN,
            step = 6
        ),
        minute_close=trial.suggest_int(
            "minute_close",
            *MINUTE_CLOSE,
            step = 6
        ),
    )

    if not valid_parameters(params):
        raise optuna.TrialPruned()

    return params


def calculate_objectives(
    result: dict,
) -> tuple[float, float, float]:
    yearly = result["yearly_returns"]

    cagrs = np.asarray(
        [
            yearly[str(year)]
            for year in range(
                TRAIN_START_YEAR,
                TRAIN_END_YEAR + 1,
            )
        ],
        dtype=float,
    )

    if not np.all(np.isfinite(cagrs)):
        raise ValueError("Non-finite yearly return")

    if np.any(cagrs <= -1.0):
        raise ValueError("Strategy reached ruin")

    logarithmic_growth = np.log1p(cagrs)

    geometric_cagr = float(
        np.expm1(np.mean(logarithmic_growth))
    )

    worst_year_cagr = float(np.min(cagrs))

    yearly_instability = float(
        np.std(logarithmic_growth, ddof=0)
    )
    
    geometric_cagr = round(geometric_cagr, 4)
    worst_year_cagr = round(worst_year_cagr, 4)
    yearly_instability = round(yearly_instability, 4)

    return (
        geometric_cagr,
        worst_year_cagr,
        yearly_instability,
    )


def objective(
    trial: optuna.Trial,
) -> tuple[float, float, float]:
    params = suggest_parameters(trial)

    result = evaluate_strategy(
        params=params,
        start_date=TRAIN_START_DATE,
        end_date=TRAIN_END_DATE,
    )

    if result["max_drawdown"] < MAX_TRAIN_DRAWDOWN:
        raise optuna.TrialPruned()
    
    
    if(result["deposited"] > result["initial_balance"] * 3): 
        print("TOOO MUCH DEPOSITED")
        print(result["initial_balance"], result["deposited"])
        print()
        raise optuna.TrialPruned()
    
    if result["full_period_cagr"] < 0.1:
        raise optuna.TrialPruned()

    values = calculate_objectives(result)

    for year, year_return in result[
        "yearly_returns"
    ].items():
        trial.set_user_attr(
            f"cagr_{year}",
            float(year_return),
        )

    trial.set_user_attr(
        "full_period_cagr",
        result["full_period_cagr"],
    )
    trial.set_user_attr(
        "max_drawdown",
        result["max_drawdown"],
    )
    trial.set_user_attr("sharpe", result["sharpe"])
    trial.set_user_attr("sortino", result["sortino"])
    trial.set_user_attr(
        "mean_trade",
        result["mean_trade"],
    )
    trial.set_user_attr(
        "days_in_position",
        result["days_in_position"],
    )
    trial.set_user_attr(
        "final_balance",
        result["final_balance"],
    )
    trial.set_user_attr(
        "deposited",
        result["deposited"],
    )
    
    return values