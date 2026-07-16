from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from backtest_adapter import evaluate_strategy
from config import (
    ARTIFACT_DIR,
    VALIDATION_END_DATE,
    VALIDATION_START_DATE,
)
from models import StrategyParams


def main() -> None:
    frozen_path = (
        ARTIFACT_DIR / "frozen_candidate.json"
    )
    output_path = (
        ARTIFACT_DIR / "validation-result.json"
    )

    if output_path.exists():
        raise FileExistsError(
            "Validation has already been run. "
            "Refusing to overwrite the original result."
        )

    with frozen_path.open(
        encoding="utf-8",
    ) as file:
        frozen = json.load(file)

    raw = frozen["parameters"]

    params = StrategyParams(
        p1=raw["p1"],
        p2=raw["p2"],
        p3=raw["p3"],
        p4=raw["p4"],
        p5=raw["p5"],
        thursday_stop=raw[
            "thursday_stop"
        ],
        friday_stop=raw[
            "friday_stop"
        ],
    )

    result = evaluate_strategy(
        params=params,
        start_date=VALIDATION_START_DATE,
        end_date=VALIDATION_END_DATE,
    )

    ytd_2026 = result[
        "yearly_returns"
    ].get("2026")

    if ytd_2026 is not None:
        start = datetime.strptime(
            "20260101",
            "%Y%m%d",
        )
        end = datetime.strptime(
            VALIDATION_END_DATE,
            "%Y%m%d",
        )

        years = (end - start).days / 365.25

        annualized_2026 = (
            (1.0 + ytd_2026) ** (1.0 / years)
            - 1.0
        )
    else:
        annualized_2026 = None

    report = {
        "candidate_sha256": frozen[
            "candidate_sha256"
        ],
        "validation_start": VALIDATION_START_DATE,
        "validation_end_exclusive": (
            VALIDATION_END_DATE
        ),
        "yearly_returns": result[
            "yearly_returns"
        ],
        "2026_ytd_return": ytd_2026,
        "2026_annualized": annualized_2026,
        "full_period_cagr": result[
            "full_period_cagr"
        ],
        "final_balance": result["final_balance"],
        "max_drawdown": result["max_drawdown"],
        "sharpe": result["sharpe"],
        "sortino": result["sortino"],
        "mean_trade": result["mean_trade"],
        "final_cagr": result["final_cagr"],
        "days_in_position": result["days_in_position"],
    }

    #with output_path.open(
    #    "x",
     #   encoding="utf-8",
    #) as file:
     #   json.dump(report, file, indent=2)

    rows = [
        {
            "year": year,
            "return": value,
        }
        for year, value in result[
            "yearly_returns"
        ].items()
    ]

    #pd.DataFrame(rows).to_csv(
    #    ARTIFACT_DIR
    #    / "validation-yearly-results.csv",
    #    index=False,
    #)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()