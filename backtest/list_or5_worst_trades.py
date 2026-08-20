"""Export worst realized trades for selected OR5 structural-exit rules."""

from __future__ import annotations

import contextlib
import csv
import io
from pathlib import Path

from optimize_oppw24_idea80_permutations import load_module


RULES = {
    "baseline": None,
    "or5_60m": {
        "opening_range_minutes": 5,
        "entry_loss": 0.005,
        "persistence": 1,
        "slow_minutes": 60,
        "slow_decline": 0.015,
    },
    "or5_75m": {
        "opening_range_minutes": 5,
        "entry_loss": 0.005,
        "persistence": 10,
        "slow_minutes": 75,
        "slow_decline": 0.015,
    },
}


def run_rule(module, quotes, rule):
    class LedgerSim(module.Sim):
        def __init__(self):
            super().__init__()
            self.ledger = []

        def sell(self, time, open_price, close_price, open_date, close_date,
                 trade_type, leverage, debug=False):
            balance_before = self.balance
            raw_return = int((close_price / open_price - 1.0) * 100000) / 100000
            result = super().sell(
                time, open_price, close_price, open_date, close_date,
                trade_type, leverage, debug,
            )
            self.ledger.append({
                "open_date": open_date,
                "close_date": close_date,
                "close_time": time,
                "exit_type": trade_type,
                "open_price": open_price,
                "close_price": close_price,
                "price_return_percent": raw_return * 100.0,
                "account_return_percent": (self.balance / balance_before - 1.0) * 100.0,
                "leverage": leverage,
            })
            return result

    sim = LedgerSim()
    sim.quotes = quotes
    with contextlib.redirect_stdout(io.StringIO()):
        sim.process(
            quotes, "QQQ", "20180413", "20260813", 8,
            (0.007, 0.02, 0.05, 0.05, 0.05),
            (100.0 - 50.0 / 8.0) / 100.0, 0.996, 0.004, 0.004,
            initial_balance=10000.0, allow_deposits=False, apply_tax=True,
            debug=False, plots=False, loss_control_lookback=None,
            arithmetic_loss_control_enabled=False, gap_momentum_enabled=True,
            tuesday_normalization_enabled=True, premarket_low_enabled=True,
            leverage_override=True, structural_exit_rule=rule,
        )
    return sorted(sim.ledger, key=lambda row: row["price_return_percent"])[:20]


def main():
    module = load_module()
    quotes = module.Sim().load_quotes("quotes.pkl")
    output = Path("../outputs/or5_worst_trades_20180413_20260812")
    output.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank", "open_date", "close_date", "close_time", "exit_type",
        "open_price", "close_price", "price_return_percent",
        "account_return_percent", "leverage",
    ]
    for name, rule in RULES.items():
        rows = run_rule(module, quotes, rule)
        with (output / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for rank, row in enumerate(rows, 1):
                writer.writerow({"rank": rank, **row})
        print(name)
        for rank, row in enumerate(rows, 1):
            print(rank, row)


if __name__ == "__main__":
    main()
