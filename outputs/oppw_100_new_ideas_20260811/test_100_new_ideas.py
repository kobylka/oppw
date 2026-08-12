import contextlib
import io
import math
import statistics
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

sys.modules.setdefault("matplotlib", types.ModuleType("matplotlib"))
sys.modules.setdefault("matplotlib.pyplot", types.ModuleType("matplotlib.pyplot"))
sys.modules.setdefault("numpy", types.ModuleType("numpy"))

from oppw24 import Sim


LEVERAGE = 11.3
START_DATE = "20180413"


class RecordingSim(Sim):
    def __init__(self):
        super().__init__()
        self.closed_trades = []

    def sell(self, time, open_price, close_price, open_date, close_date,
             trade_type, leverage, debug=False):
        raw = int((close_price / open_price - 1) * 100000) / 100000
        self.closed_trades.append({
            "open_date": open_date,
            "close_date": close_date,
            "raw": raw,
            "exit": trade_type,
        })
        return super().sell(time, open_price, close_price, open_date,
                            close_date, trade_type, leverage, debug)


def run_baseline(quotes):
    sim = RecordingSim()
    sim.quotes = quotes
    last = datetime.strptime(max(quotes), "%Y%m%d").date()
    with contextlib.redirect_stdout(io.StringIO()):
        sim.process(
            {}, "QQQ", START_DATE,
            (last + timedelta(days=1)).strftime("%Y%m%d"),
            LEVERAGE, [0.007, 0.02, 0.05, 0.05, 0.05],
            (100 - 50 / LEVERAGE) / 100, 0.996, 0.004, 0.004,
            initial_balance=30000, allow_deposits=False, apply_tax=False,
            debug=False, plots=False,
        )
    return sim


def safe_div(numerator, denominator, default=0.0):
    return numerator / denominator if abs(denominator) > 1e-15 else default


def median(values):
    return statistics.median(values) if values else 0.0


def mean(values):
    return statistics.fmean(values) if values else 0.0


def stdev(values):
    return statistics.pstdev(values) if len(values) > 1 else 0.0


def skew(values):
    sigma = stdev(values)
    if len(values) < 3 or sigma == 0:
        return 0.0
    mu = mean(values)
    return mean([((value - mu) / sigma) ** 3 for value in values])


def kurtosis(values):
    sigma = stdev(values)
    if len(values) < 4 or sigma == 0:
        return 0.0
    mu = mean(values)
    return mean([((value - mu) / sigma) ** 4 for value in values])


def autocorrelation(values):
    if len(values) < 3:
        return 0.0
    left = values[:-1]
    right = values[1:]
    ml = mean(left)
    mr = mean(right)
    numerator = sum((a - ml) * (b - mr) for a, b in zip(left, right))
    denominator = math.sqrt(
        sum((a - ml) ** 2 for a in left)
        * sum((b - mr) ** 2 for b in right)
    )
    return safe_div(numerator, denominator)


def sign_entropy(values):
    if not values:
        return 0.0
    positive = sum(value > 0 for value in values)
    negative = sum(value < 0 for value in values)
    count = positive + negative
    if count == 0:
        return 0.0
    result = 0.0
    for observations in (positive, negative):
        if observations:
            probability = observations / count
            result -= probability * math.log2(probability)
    return result


def variance_ratio_2(values):
    if len(values) < 6:
        return 1.0
    one_var = statistics.pvariance(values)
    paired = [values[index] + values[index + 1]
              for index in range(0, len(values) - 1, 2)]
    return safe_div(statistics.pvariance(paired), 2 * one_var, 1.0)


def sign_changes(values):
    signs = [1 if value > 0 else -1 if value < 0 else 0 for value in values]
    signs = [value for value in signs if value]
    return sum(a != b for a, b in zip(signs, signs[1:]))


def bar_return(candles, start, end):
    return safe_div(candles[end][3], candles[start][0], 1.0) - 1.0


def path_efficiency(candles):
    closes = [candle[3] for candle in candles]
    if len(closes) < 2:
        return 0.0
    traveled = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
    return safe_div(abs(closes[-1] - candles[0][0]), traveled)


def block_returns(candles, block_size=30):
    result = []
    for start in range(0, len(candles), block_size):
        block = candles[start:start + block_size]
        if block:
            result.append(safe_div(block[-1][3], block[0][0], 1.0) - 1.0)
    return result


def session_record(day_quotes):
    cash = day_quotes[934:1325]
    o = cash[0][0]
    c = cash[-1][3]
    h = max(candle[1] for candle in cash)
    l = min(candle[2] for candle in cash)
    span = h - l
    first_hour = cash[:60]
    middle = cash[60:-60]
    last_hour = cash[-60:]
    blocks = block_returns(cash)
    return {
        "o": o,
        "h": h,
        "l": l,
        "c": c,
        "ret": safe_div(c, o, 1.0) - 1.0,
        "range": safe_div(span, o),
        "body": safe_div(abs(c - o), span),
        "loc": safe_div(c - l, span, 0.5),
        "upper": safe_div(h - max(o, c), span),
        "lower": safe_div(min(o, c) - l, span),
        "first_hour": safe_div(first_hour[-1][3], first_hour[0][0], 1.0) - 1.0,
        "middle": safe_div(middle[-1][3], middle[0][0], 1.0) - 1.0,
        "last_hour": safe_div(last_hour[-1][3], last_hour[0][0], 1.0) - 1.0,
        "high_pos": max(range(len(cash)), key=lambda i: cash[i][1]) / (len(cash) - 1),
        "low_pos": min(range(len(cash)), key=lambda i: cash[i][2]) / (len(cash) - 1),
        "eff": path_efficiency(cash),
        "last_range_share": safe_div(
            max(x[1] for x in last_hour) - min(x[2] for x in last_hour), span
        ),
        "block_changes": sign_changes(blocks),
    }


def premarket_record(day_quotes, previous_close):
    candles = day_quotes[4:934]
    o = candles[0][0]
    c = candles[-1][3]
    h = max(candle[1] for candle in candles)
    l = min(candle[2] for candle in candles)
    span = h - l
    cash_open = day_quotes[934][0]
    blocks = block_returns(candles, 60)
    return {
        "ret": safe_div(c, o, 1.0) - 1.0,
        "range": safe_div(span, o),
        "loc": safe_div(c - l, span, 0.5),
        "eff": path_efficiency(candles),
        "high_pos": max(range(len(candles)), key=lambda i: candles[i][1]) / (len(candles) - 1),
        "low_pos": min(range(len(candles)), key=lambda i: candles[i][2]) / (len(candles) - 1),
        "last60": safe_div(candles[-1][3], candles[-60][0], 1.0) - 1.0,
        "open_jump": safe_div(cash_open, c, 1.0) - 1.0,
        "overnight": safe_div(cash_open, previous_close, 1.0) - 1.0,
        "block_changes": sign_changes(blocks),
    }


def make_signals(index, dates, sessions, quotes):
    history = sessions[index - 40:index]
    previous = history[-1]
    p2 = history[-2]
    p3 = history[-3]
    current_pre = premarket_record(quotes[dates[index]]["QQQ"], previous["c"])

    closes = [item["c"] for item in history]
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    ret20 = returns[-20:]
    ret10 = returns[-10:]
    ranges20 = [item["range"] for item in history[-20:]]
    med_range = median(ranges20)
    sigma20 = stdev(ret20)
    sigma5 = stdev(ret20[-5:])
    downside = mean([value * value for value in ret20 if value < 0])
    upside = mean([value * value for value in ret20 if value > 0])
    range_vol = stdev(ranges20)
    close_path = closes[-21:]
    path_distance = sum(abs(b - a) for a, b in zip(close_path, close_path[1:]))
    close_eff = safe_div(abs(close_path[-1] - close_path[0]), path_distance)
    ret1 = ret20[-1]
    negative_count = sum(value < 0 for value in ret10)

    prev_gap = previous["o"] / p2["c"] - 1.0
    inside1 = previous["h"] < p2["h"] and previous["l"] > p2["l"]
    inside2 = p2["h"] < p3["h"] and p2["l"] > p3["l"]
    narrowed = previous["range"] < p2["range"] < p3["range"]

    s = {}
    names = {}

    def add(number, name, value):
        s[number] = bool(value)
        names[number] = name

    add(1, "Previous bearish marubozu", previous["ret"] <= -0.008 and previous["body"] >= 0.65 and previous["loc"] <= 0.20)
    add(2, "Previous bullish marubozu", previous["ret"] >= 0.008 and previous["body"] >= 0.65 and previous["loc"] >= 0.80)
    add(3, "Upper-wick rejection on above-median range", previous["upper"] >= 0.45 and previous["loc"] <= 0.45 and previous["range"] >= med_range)
    add(4, "Lower-wick rejection on above-median range", previous["lower"] >= 0.45 and previous["loc"] >= 0.55 and previous["range"] >= med_range)
    add(5, "Bearish outside session", previous["h"] > p2["h"] and previous["l"] < p2["l"] and previous["c"] < previous["o"])
    add(6, "Bullish outside session", previous["h"] > p2["h"] and previous["l"] < p2["l"] and previous["c"] > previous["o"])
    add(7, "Inside session after wide session", inside1 and p2["range"] >= 1.5 * med_range)
    add(8, "Two consecutive inside sessions", inside1 and inside2)
    add(9, "Downside range expansion", previous["range"] >= 1.5 * med_range and previous["loc"] <= 0.25)
    add(10, "Upside range expansion", previous["range"] >= 1.5 * med_range and previous["loc"] >= 0.75)
    add(11, "Wide doji", previous["body"] <= 0.15 and previous["range"] >= 1.3 * med_range)
    add(12, "Compressed doji", previous["body"] <= 0.15 and previous["range"] <= 0.70 * med_range)
    add(13, "Two consecutive upper-wick rejections", previous["upper"] >= 0.35 and p2["upper"] >= 0.35)
    add(14, "Two consecutive lower-wick rejections", previous["lower"] >= 0.35 and p2["lower"] >= 0.35)
    add(15, "Two of three closes in bottom quartile", sum(x["loc"] <= 0.25 for x in (previous, p2, p3)) >= 2)
    add(16, "Two of three closes in top quartile", sum(x["loc"] >= 0.75 for x in (previous, p2, p3)) >= 2)
    add(17, "Three-session narrowing ending bearish", narrowed and previous["ret"] < 0)
    add(18, "Three-session narrowing ending bullish", narrowed and previous["ret"] > 0)
    add(19, "Previous gap-up fully faded", prev_gap >= 0.005 and previous["c"] < p2["c"])
    add(20, "Previous gap-down fully recovered", prev_gap <= -0.005 and previous["c"] > p2["c"])

    add(21, "Early rally followed by late selloff", previous["first_hour"] >= 0.005 and previous["last_hour"] <= -0.005)
    add(22, "Early selloff followed by late rebound", previous["first_hour"] <= -0.005 and previous["last_hour"] >= 0.005)
    add(23, "Previous last-hour selloff", previous["last_hour"] <= -0.007)
    add(24, "Previous last-hour surge", previous["last_hour"] >= 0.007)
    add(25, "Morning rally and midday fade", previous["first_hour"] >= 0.005 and previous["middle"] <= -0.007)
    add(26, "Morning selloff and midday rebound", previous["first_hour"] <= -0.005 and previous["middle"] >= 0.007)
    add(27, "Early high and bottom-quartile close", previous["high_pos"] <= 0.30 and previous["loc"] <= 0.25)
    add(28, "Early low and top-quartile close", previous["low_pos"] <= 0.30 and previous["loc"] >= 0.75)
    add(29, "Directional down session from early high to late low", previous["high_pos"] <= 0.25 and previous["low_pos"] >= 0.75)
    add(30, "Directional up session from early low to late high", previous["low_pos"] <= 0.25 and previous["high_pos"] >= 0.75)
    add(31, "High-efficiency down cash session", previous["ret"] <= -0.005 and previous["eff"] >= 0.10)
    add(32, "High-efficiency up cash session", previous["ret"] >= 0.005 and previous["eff"] >= 0.10)
    add(33, "Wide but inefficient cash session", previous["range"] >= 1.2 * med_range and previous["eff"] <= 0.15)
    add(34, "Down session with last-hour range concentration", previous["ret"] < 0 and previous["last_range_share"] >= 0.45)
    add(35, "Up session with last-hour range concentration", previous["ret"] > 0 and previous["last_range_share"] >= 0.45)
    add(36, "High intraday 30-minute reversal count", previous["block_changes"] >= 8)
    add(37, "Low-reversal directional down session", previous["block_changes"] <= 2 and previous["ret"] <= -0.005)
    add(38, "Low-reversal directional up session", previous["block_changes"] <= 2 and previous["ret"] >= 0.005)
    add(39, "Late rejection at least 1% below session high", previous["high_pos"] >= 0.50 and previous["c"] / previous["h"] - 1 <= -0.01)
    add(40, "Late recovery at least 1% above session low", previous["low_pos"] >= 0.50 and previous["c"] / previous["l"] - 1 >= 0.01)

    add(41, "Efficient premarket decline", current_pre["ret"] <= -0.008 and current_pre["eff"] >= 0.06)
    add(42, "Efficient premarket advance", current_pre["ret"] >= 0.008 and current_pre["eff"] >= 0.06)
    add(43, "Wide choppy premarket", current_pre["range"] >= 0.015 and current_pre["eff"] <= 0.15)
    add(44, "Premarket V-recovery from low", current_pre["low_pos"] <= 0.65 and current_pre["loc"] >= 0.75 and current_pre["range"] >= 0.01)
    add(45, "Premarket inverted-V rejection", current_pre["high_pos"] <= 0.65 and current_pre["loc"] <= 0.25 and current_pre["range"] >= 0.01)
    add(46, "Premarket final-hour selloff", current_pre["last60"] <= -0.005)
    add(47, "Premarket final-hour surge", current_pre["last60"] >= 0.005)
    add(48, "Cash open jumps above final premarket print", current_pre["open_jump"] >= 0.00010)
    add(49, "Cash open drops below final premarket print", current_pre["open_jump"] <= -0.00010)
    add(50, "Premarket closes near its low", current_pre["loc"] <= 0.15 and current_pre["range"] >= 0.008)
    add(51, "Premarket closes near its high", current_pre["loc"] >= 0.85 and current_pre["range"] >= 0.008)
    add(52, "Overnight rise contradicted by premarket decline", current_pre["overnight"] >= 0.005 and current_pre["ret"] <= -0.003)
    add(53, "Overnight decline contradicted by premarket rise", current_pre["overnight"] <= -0.005 and current_pre["ret"] >= 0.003)
    add(54, "Premarket high early and close near low", current_pre["high_pos"] <= 0.35 and current_pre["loc"] <= 0.20)
    add(55, "Premarket low early and close near high", current_pre["low_pos"] <= 0.35 and current_pre["loc"] >= 0.80)
    add(56, "Premarket range exceeds previous cash range", current_pre["range"] >= previous["range"])
    add(57, "Compressed premarket followed by opening discontinuity", current_pre["range"] <= 0.35 * previous["range"] and abs(current_pre["open_jump"]) >= 0.00008)
    add(58, "High premarket hourly reversal count", current_pre["block_changes"] >= 8)
    add(59, "Very efficient premarket decline", current_pre["ret"] <= -0.004 and current_pre["eff"] >= 0.09)
    add(60, "Very efficient premarket advance", current_pre["ret"] >= 0.004 and current_pre["eff"] >= 0.09)

    add(61, "Strong negative 20-session return skew", skew(ret20) <= -1.0)
    add(62, "Strong positive 20-session return skew", skew(ret20) >= 1.0)
    add(63, "High 20-session kurtosis with latest decline", kurtosis(ret20) >= 4.5 and ret1 < 0)
    add(64, "Downward statistical jump", sigma20 > 0 and ret1 <= -2.0 * sigma20)
    add(65, "Upward statistical jump", sigma20 > 0 and ret1 >= 2.0 * sigma20)
    add(66, "Downside semivariance dominates", downside >= 2.0 * upside and downside > 0)
    add(67, "Upside semivariance dominates", upside >= 2.0 * downside and upside > 0)
    add(68, "Five-session volatility expansion after decline", sigma20 > 0 and sigma5 >= 1.5 * sigma20 and ret1 < 0)
    add(69, "Five-session volatility expansion after advance", sigma20 > 0 and sigma5 >= 1.5 * sigma20 and ret1 > 0)
    add(70, "Volatility contraction with low previous close", sigma20 > 0 and sigma5 <= 0.60 * sigma20 and previous["loc"] <= 0.30)
    add(71, "High range-volatility with low previous close", range_vol >= 0.55 * med_range and previous["loc"] <= 0.25)
    add(72, "Negative return autocorrelation after decline", autocorrelation(ret10) <= -0.35 and ret1 < 0)
    add(73, "Positive return autocorrelation after decline", autocorrelation(ret10) >= 0.35 and ret1 < 0)
    add(74, "Low sign entropy with negative majority", sign_entropy(ret10) <= 0.75 and negative_count >= 7)
    add(75, "High sign entropy after wide session", sign_entropy(ret10) >= 0.97 and previous["range"] >= 1.2 * med_range)
    add(76, "Two-period mean-reversion variance ratio after decline", variance_ratio_2(ret20) <= 0.65 and ret1 < 0)
    add(77, "Two-period trending variance ratio after decline", variance_ratio_2(ret20) >= 1.40 and ret1 < 0)
    add(78, "Efficient 20-session declining path", close_eff >= 0.35 and closes[-1] < closes[-21])
    add(79, "Cluster of downside-tail sessions", sigma20 > 0 and sum(x <= -1.5 * sigma20 for x in ret20) >= 3)
    add(80, "Cluster of upside-tail sessions", sigma20 > 0 and sum(x >= 1.5 * sigma20 for x in ret20) >= 3)

    chains = [
        (81, "Bearish marubozu plus efficient premarket decline", s[1] and s[41]),
        (82, "Bullish marubozu plus premarket inverted-V", s[2] and s[45]),
        (83, "Prior gap-up fade or premarket final-hour selloff", s[19] or s[46]),
        (84, "Wide doji plus directional premarket", s[11] and (s[41] or s[42])),
        (85, "Choppy wide cash session plus opening discontinuity", s[33] and (s[48] or s[49])),
        (86, "Down-volatility expansion or premarket selloff", s[68] or s[46]),
        (87, "Negative skew plus downward statistical jump", s[61] and s[64]),
        (88, "Downside-tail cluster plus downside range expansion", s[79] and s[9]),
        (89, "Negative autocorrelation plus upper-wick rejection", s[72] and s[3]),
        (90, "Efficient 20-session decline plus weak premarket close", s[78] and s[50]),
        (91, "Previous last-hour and current premarket selloffs", s[23] and s[41]),
        (92, "Directional down session or overnight-up contradiction", s[29] or s[52]),
        (93, "Late downside range concentration plus premarket selloff", s[34] and s[46]),
        (94, "Downward jump followed by premarket V-recovery", s[64] and s[44]),
        (95, "Volatility contraction followed by wide choppy premarket", s[70] and s[43]),
        (96, "Inside session followed by opening discontinuity", s[7] and (s[48] or s[49])),
        (97, "Repeated low closes plus weak premarket close", s[15] and s[50]),
        (98, "High reversal counts in cash and premarket", s[36] and s[58]),
        (99, "Bearish rejection or downward opening discontinuity", s[3] or s[5] or s[49]),
        (100, "Bullish rejection plus upward opening discontinuity", (s[4] or s[6]) and s[48]),
    ]
    for number, name, value in chains:
        add(number, name, value)

    return s, names


def compounded(values):
    return math.prod(1.0 + value for value in values)


def weekly_geometric(values):
    growth = compounded(values)
    return growth ** (1 / len(values)) - 1 if growth > 0 and values else -1.0


def max_drawdown(values):
    equity = peak = 1.0
    worst = 0.0
    for value in values:
        equity *= 1 + value
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
    return worst


def worst_52(values):
    if len(values) < 52:
        return compounded(values) - 1
    return min(compounded(values[i:i + 52]) - 1 for i in range(len(values) - 51))


def metrics(values):
    return {
        "geo": weekly_geometric(values),
        "dd": max_drawdown(values),
        "worst52": worst_52(values),
    }


def main():
    quotes = Sim().load_quotes("quotes.pkl")
    dates = sorted(quotes)
    sessions = [session_record(quotes[day]["QQQ"]) for day in dates]
    positions = {day: index for index, day in enumerate(dates)}
    baseline = run_baseline(quotes)

    trades = []
    idea_names = None
    for trade in baseline.closed_trades:
        index = positions[trade["open_date"]]
        if index >= 40:
            signals, names = make_signals(index, dates, sessions, quotes)
            idea_names = names
        else:
            signals = None
        trades.append({
            "date": trade["open_date"],
            "return": trade["raw"] * LEVERAGE,
            "signals": signals,
        })

    for trade in trades:
        if trade["signals"] is None:
            trade["signals"] = {number: False for number in range(1, 101)}

    baseline_values = [trade["return"] for trade in trades]
    base_metrics = metrics(baseline_values)
    post2021_indices = [i for i, trade in enumerate(trades) if trade["date"] >= "20210101"]
    period_2022_2025 = [i for i, trade in enumerate(trades)
                        if "20220101" <= trade["date"] < "20260101"]

    results = []
    for number in range(1, 101):
        mask = [trade["signals"][number] for trade in trades]
        values = [0.0 if skip else trade["return"]
                  for trade, skip in zip(trades, mask)]
        result_metrics = metrics(values)
        skipped_returns = [trade["return"] for trade, skip in zip(trades, mask) if skip]
        post2021 = [values[i] for i in post2021_indices]
        y2022_2025 = [values[i] for i in period_2022_2025]
        results.append({
            "id": number,
            "name": idea_names[number],
            "skips": sum(mask),
            "skipped_losses": sum(value < 0 for value in skipped_returns),
            "skipped_wins": sum(value > 0 for value in skipped_returns),
            "geo": result_metrics["geo"],
            "geo_delta": result_metrics["geo"] - base_metrics["geo"],
            "dd": result_metrics["dd"],
            "dd_delta": result_metrics["dd"] - base_metrics["dd"],
            "worst52": result_metrics["worst52"],
            "worst52_delta": result_metrics["worst52"] - base_metrics["worst52"],
            "post2021_geo": weekly_geometric(post2021),
            "y2022_2025_geo": weekly_geometric(y2022_2025),
        })

    results.sort(key=lambda row: (row["geo"], row["dd_delta"]), reverse=True)
    print("BASELINE")
    print("trades", len(trades))
    for name, value in base_metrics.items():
        print(name, f"{value:.12f}")
    print("RESULTS")
    print("rank|id|name|skips|losses|wins|geo_pct|delta_pp|dd_pct|dd_improve_pp|worst52_pct|worst52_improve_pp|post2021_geo_pct|2022_2025_geo_pct")
    for rank, row in enumerate(results, 1):
        print(
            f"{rank}|{row['id']}|{row['name']}|{row['skips']}|"
            f"{row['skipped_losses']}|{row['skipped_wins']}|"
            f"{100 * row['geo']:.6f}|{100 * row['geo_delta']:.6f}|"
            f"{100 * row['dd']:.4f}|{100 * row['dd_delta']:.4f}|"
            f"{100 * row['worst52']:.4f}|{100 * row['worst52_delta']:.4f}|"
            f"{100 * row['post2021_geo']:.6f}|{100 * row['y2022_2025_geo']:.6f}"
        )

    output_dir = Path("..") / "outputs" / "oppw_100_new_ideas_20260811"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "results.md"
    report = [
        "# OPPW: 100 new causal entry-skip ideas",
        "",
        "Generated 2026-08-11 from `backtest/quotes.pkl` using the current "
        "`oppw24.py` baseline from 2018-04-13 through the last completed trade.",
        "",
        "Each idea is a standalone causal entry gate. When its signal is true at "
        "the weekly cash open, that week's baseline entry is replaced by a 0% "
        "return. Signals use only prior completed sessions and the current "
        "premarket. Results use fixed 11.3x leverage and no tax or deposits.",
        "",
        "Previously explored last-N loss gates, plain opening-gap gates, simple "
        "momentum/MA/RSI/ATR gates, Tuesday re-entry, and long-market-break rules "
        "were deliberately excluded.",
        "",
        "## Baseline",
        "",
        f"- Completed weekly trades: {len(trades)}",
        f"- Weekly geometric return: {100 * base_metrics['geo']:.6f}%",
        f"- Weekly-close maximum drawdown: {100 * base_metrics['dd']:.4f}%",
        f"- Worst rolling 52 observed weeks: {100 * base_metrics['worst52']:.4f}%",
        "",
        "## Ranked results",
        "",
        "|Rank|ID|Idea|Skips|Skipped L/W|Weekly geo|Delta|Max DD|DD improvement|Worst 52|Worst-52 improvement|Post-2021 geo|2022-2025 geo|",
        "|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(results, 1):
        report.append(
            f"|{rank}|{row['id']}|{row['name']}|{row['skips']}|"
            f"{row['skipped_losses']}/{row['skipped_wins']}|"
            f"{100 * row['geo']:.6f}%|{100 * row['geo_delta']:+.6f} pp|"
            f"{100 * row['dd']:.4f}%|{100 * row['dd_delta']:+.4f} pp|"
            f"{100 * row['worst52']:.4f}%|{100 * row['worst52_delta']:+.4f} pp|"
            f"{100 * row['post2021_geo']:.6f}%|"
            f"{100 * row['y2022_2025_geo']:.6f}%|"
        )
    report.extend([
        "",
        "## Interpretation limits",
        "",
        "These are exploratory in-sample screens over 100 hypotheses. Ranking "
        "does not constitute untouched out-of-sample confirmation. Thresholds "
        "must be frozen before walk-forward or live shadow evaluation.",
        "",
        "The accompanying `test_100_new_ideas.py` contains every exact causal "
        "formula and threshold used for this report.",
        "",
    ])
    report_path.write_text("\n".join(report), encoding="utf-8")
    print("REPORT", report_path.resolve())


if __name__ == "__main__":
    main()
