"""Evaluate 100 new volatility and market-structure exits."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import sys
import types
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def load_module():
    matplotlib = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    for name in ("plot", "xlabel", "ylabel", "title", "legend", "grid", "show"):
        setattr(pyplot, name, lambda *args, **kwargs: None)
    matplotlib.pyplot = pyplot
    sys.modules.setdefault("matplotlib", matplotlib)
    sys.modules.setdefault("matplotlib.pyplot", pyplot)
    import oppw24
    return oppw24


def make_ideas():
    result = []
    number = 1
    for multiple in (0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0, 1.25, 1.5, 2.0,
                     2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0,
                     9.0, 10.0, 12.0, 15.0, 20.0):
        result.append({"idea_id": number, "family": "previous_range_stop", "rule": {
            "family": "previous_range_stop", "multiple": multiple,
        }}); number += 1
    for minimum_expansion in (0.005, 0.01, 0.015, 0.02, 0.03):
        for retracement in (0.005, 0.0075, 0.01, 0.015, 0.02):
            result.append({"idea_id": number, "family": "range_expansion_reversal", "rule": {
                "family": "range_expansion_reversal", "minimum_minutes": 30,
                "minimum_expansion": minimum_expansion, "retracement": retracement,
            }}); number += 1
    for count in (2, 3, 4, 5, 7):
        for decline in (0.0025, 0.005, 0.0075, 0.01, 0.015):
            result.append({"idea_id": number, "family": "lower_close_sequence", "rule": {
                "family": "lower_close_sequence", "count": count,
                "minimum_decline": decline,
            }}); number += 1
    for buffer in (0.0, 0.0025, 0.005, 0.0075, 0.01):
        for persistence in (1, 3, 5, 10, 15):
            result.append({"idea_id": number, "family": "previous_low_break", "rule": {
                "family": "previous_low_break", "buffer": buffer,
                "persistence": persistence,
            }}); number += 1
    if len(result) != 100: raise AssertionError(len(result))
    for item in result: item["description"] = json.dumps(item["rule"], sort_keys=True)
    return result


def daily_dd(points):
    peak=10000.0; maximum=0.0
    for _, equity in points:
        equity=float(equity)
        if equity>peak: peak=equity
        elif peak>0: maximum=max(maximum,1.0-equity/peak)
    return maximum


def run_one(module,quotes,idea,start="20180413"):
    sim=module.Sim(); sim.quotes=quotes
    with contextlib.redirect_stdout(io.StringIO()):
        sim.process(quotes,"QQQ",start,"20260813",8,(.007,.02,.05,.05,.05),(100-50/8)/100,.996,.004,.004,
            initial_balance=10000.0,allow_deposits=False,apply_tax=True,debug=False,plots=False,
            loss_control_lookback=None,arithmetic_loss_control_enabled=False,gap_momentum_enabled=True,
            tuesday_normalization_enabled=True,premarket_low_enabled=True,leverage_override=True,
            market_structure_exit_rule=None if idea is None else idea["rule"])
    years=sim.week_no*7/365; cagr=((sim.balance/sim.deposited)**(1/years)-1)*100
    return {"idea_id":0 if idea is None else idea["idea_id"],"family":"baseline" if idea is None else idea["family"],
        "description":"No market structure exit" if idea is None else idea["description"],"final_balance":sim.balance,
        "deposited":sim.deposited,"cagr_percent":cagr,"daily_drawdown":daily_dd(sim.daily_equity_points),
        "closed_drawdown":1-sim.max_dd,"trades":sim.trade_no,"days_in_position":sim.days_in_position}


def worker(path,assigned):
    module=load_module(); seed=module.Sim(); quotes=seed.load_quotes(str(path))
    return [run_one(module,quotes,idea) for idea in assigned]


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--quotes",type=Path,default=Path("quotes.pkl")); parser.add_argument("--output",type=Path,required=True); args=parser.parse_args()
    all_ideas=make_ideas(); module=load_module(); seed=module.Sim(); quotes=seed.load_quotes(str(args.quotes.resolve())); baseline=run_one(module,quotes,None)
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker,args.quotes.resolve(),all_ideas[:50]),pool.submit(worker,args.quotes.resolve(),all_ideas[50:])]
        rows=futures[0].result()+futures[1].result()
    for row in rows:
        row["dd_improvement_pp"]=(baseline["daily_drawdown"]-row["daily_drawdown"])*100
        row["cagr_change_pp"]=row["cagr_percent"]-baseline["cagr_percent"]
        row["cagr_retention"]=row["cagr_percent"]/baseline["cagr_percent"]
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    (output/"results.json").write_text(json.dumps({"baseline":baseline,"ideas":rows},indent=2),encoding="utf-8")
    with (output/"results.csv").open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"baseline":baseline,"improved":sum(r["dd_improvement_pp"]>0 for r in rows)})); return 0


if __name__=="__main__": raise SystemExit(main())
