from __future__ import annotations

import pickle
from functools import lru_cache

from config import (
    ALLOW_DEPOSITS,
    APPLY_TAX,
    BREAK_EVEN_RATIO,
    DISASTER_STOP_RATIO,
    INITIAL_BALANCE,
    LEVERAGE,
    QUOTES_CACHE,
)
from models import StrategyParams
from strategy import Sim


@lru_cache(maxsize=1)
def load_quotes() -> dict:
    if not QUOTES_CACHE.exists():
        raise FileNotFoundError(
            f"Run prepare_quotes.py first: {QUOTES_CACHE}"
        )

    with QUOTES_CACHE.open("rb") as file:
        return pickle.load(file)


def evaluate_strategy(
    params: StrategyParams,
    start_date: str,
    end_date: str,
) -> dict:
    sim = Sim()

    # Shared read-only dictionary. Do not modify quotes in process().
    sim.quotes = load_quotes()

    return sim.process(
        quotes=sim.quotes,
        stock="SPY",
        start_date=start_date,
        end_date=end_date,
        leverage=LEVERAGE,
        tpps=params.tpps,
        disaster_stop_ratio=DISASTER_STOP_RATIO,
        BE=BREAK_EVEN_RATIO,
        thursday_stop=(
            params.thursday_stop_fraction
        ),
        friday_stop=(
            params.friday_stop_fraction
        ),
        initial_balance=INITIAL_BALANCE,
        allow_deposits=ALLOW_DEPOSITS,
        apply_tax=APPLY_TAX,
        debug=False,
        plots=False,
    )