from datetime import datetime, timedelta
import os
import matplotlib.pyplot as plt
import numpy as np
import math
import random
import pickle
from collections import deque
from pathlib import Path

def plotting(equity_history,deposit_history):
        y = np.array(equity_history)
        z = np.array(deposit_history)
        x = np.arange(1, len(equity_history)+1)

        # Plotting the two arrays
        plt.plot(x, y, z, label='y = x')
        plt.xlabel('x')
        plt.ylabel('y')
        plt.title('Plot of y = x')
        plt.legend()
        plt.grid(True)
        plt.show()

class Sim:
    def __init__(self):
        self.quotes = {}

        self.wallet = {}
        self.stocks = []
        self.transactions = []
        self.balance = 0
        self.deposited = 0
        self.transaction_n = 0
        self.timeouts = 0
        self.profits = 0
        self.gained = 0
        self.max_equity = 0
        self.local_dd_equity = 1000000000000
        self.n=0
        self.trade_no=0
        self.break_even = False
        
        self.cumulative_change = 1
        
        self.classA = 0
        self.classB = 0
        self.classC = 0
        self.classD = 0
        
        self.prev_change = 0
        self.prev_open = 0
            
        self.lost = 0
        self.dd = 0
        
        self.wins = []
        self.loses = []
            
        self.equity_history = []
        self.deposit_history = []
    
    def load_quotes(self, filename: str = "quotes.pkl") -> dict:
        path = Path(filename)

        if path.exists():
            with path.open("rb") as file:
                quotes = pickle.load(file)

            if not isinstance(quotes, dict):
                raise TypeError("Loaded object is not a dictionary")

            self.quotes = quotes
            return quotes
        return {}
        
    def save_quotes(self, filename: str = "quotes.pkl") -> None:
        path = Path(filename)

        with path.open("wb") as file:
            pickle.dump(
                self.quotes,
                file,
                protocol=pickle.HIGHEST_PROTOCOL
            )
        
    def read_csv_quotes(self, files, start_date):
        # start_date as 'DD.MM.YYYY'
        for f in files:
            fname = f.split(".")
            if fname[-1] in ["csv", "txt"]:
                stock = fname[0].upper()
                if stock not in self.stocks:
                    self.stocks.append(stock)
            else:
                continue
            
            with open(f, encoding='utf-8') as file:
                init = False
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split(";")
                    if len(parts) < 6:
                        continue

                    dukascopy_date = parts[0].strip()  # '03.01.2022'
                    date = dukascopy_date
                    
                    if date == "20200309": continue
                    if date == "20200310": continue
                    if date == "20200311": continue
                    if date == "20200312": continue
                    if date == "20200313": continue
                    if date == "20200316": continue
                    if date == "20200317": continue
                    if date == "20200318": continue
                    if date == "20200319": continue
                    if date == "20200320": continue
                    if date == "20251128": continue
                    
                    if date == start_date:
                        init = True
                    if not init:
                        continue

                    try:
                        o = float(parts[2])
                        h = float(parts[3])
                        l = float(parts[4])
                        c = float(parts[5])
                    except ValueError:
                        continue
                    # Create nested structures if needed
                    if date not in self.quotes:
                        self.quotes[date] = {}
                    if stock not in self.quotes[date]:
                        self.quotes[date][stock] = []  # List of hourly bars
                    #print(self.quotes[date][stock])
                    # Append this hour's data
                    self.quotes[date][stock].append([o, h, l, c])
            
        self.save_quotes()
                        
    def sharpe_ratio(self, returns, risk_free_annual=0.0, periods_per_year=52):
        r = np.array(returns, dtype=float)

        rf_period = (1 + risk_free_annual) ** (1 / periods_per_year) - 1
        excess = r - rf_period

        if len(excess) < 2:
            return np.nan

        std = np.std(excess, ddof=1)
        if std == 0:
            return np.nan

        return np.mean(excess) / std * np.sqrt(periods_per_year)
        
    def sortino_ratio(self, returns, risk_free_annual=0.0, periods_per_year=52, target_annual=0.0):
        r = np.array(returns, dtype=float)

        rf_period = (1 + risk_free_annual) ** (1 / periods_per_year) - 1
        target_period = (1 + target_annual) ** (1 / periods_per_year) - 1

        excess = r - rf_period
        downside = np.minimum(0, r - target_period)

        downside_dev = np.sqrt(np.mean(downside ** 2))

        if downside_dev == 0:
            return np.nan

        return np.mean(excess) / downside_dev * np.sqrt(periods_per_year)
    
    def process(
        self,
        quotes,
        stock,
        start_date,
        end_date,
        initial_balance=12000.0,
        n=3,
        m=30,
        stop_loss_pct = 0.005,
        take_profit_pct = 0.005,
        leverage=6,
        plot=False,
        LONG_ONLY=False
    ):
        self.trade_returns = []
        self.daily_equity_points = []
        self.leverage = leverage
        
        self.days_in_position = 0
        
        self.wallet = {}
        self.stocks = []
        self.transactions = []
        self.balance = 0
        self.deposited = 0
        self.transaction_n = 0
        self.timeouts = 0
        self.profits = 0
        self.gained = 0
        self.max_equity = 0
        self.local_dd_equity = 1000000000000
        self.n=0
        self.trade_no=0
        self.break_even = False
        
        self.cumulative_change = 1
        
        self.classA = 0
        self.classB = 0
        self.classC = 0
        self.classD = 0
        
        self.prev_change = 0
        self.prev_full_week_change = 0
            
        self.lost = 0
        self.dd = 0
            
        self.equity_history = []
        self.deposit_history = []
        
        prev_date = "20000101"
        prev_year = start_date
        
        
        self.classA = 0
        self.classB = 0
        self.classC = 0
        self.classD = 0  
            
        self.deposited = initial_balance
        self.balance   = initial_balance
        trade_type = ""
        
        self.max_dd = 1
        self.dd_current_duration = 0
        self.dd_total_duration = 0
        self.max_dd_duration = 0
        
        date = ""
        
        open_price = 0
        qqq_open_price = 0
        
        yearlies = []
        self.returns = []
        prev_year = start_date
        
        prev_equity = initial_balance
        
        # ================================================================
        # SETTINGS
        # ================================================================


        slippage = 2

        entry_i_start = 885
        entry_i_end = 1330

        max_long_entries_per_day = 2
        max_short_entries_per_day = 2

        verbose = False


        # ================================================================
        # STATISTICS
        # ================================================================

        long_returns = []
        short_returns = []

        long_raw_returns = []
        short_raw_returns = []

        long_entries_per_day = {}
        short_entries_per_day = {}

        long_stop_count = 0
        short_stop_count = 0

        long_tp_count = 0
        short_tp_count = 0

        long_timeout_count = 0
        short_timeout_count = 0


        # ================================================================
        # BUILD FLATTENED DATA ONCE
        #
        # If this strategy is called thousands of times with the same
        # stock/start/end data, this section only runs the first time.
        # ================================================================

        if not hasattr(self, "_breakout_flat_cache"):
            self._breakout_flat_cache = {}

        cache_key = (stock, start_date, end_date)

        if cache_key not in self._breakout_flat_cache:

            dates = []
            candle_indices = []

            opens = []
            highs = []
            lows = []
            closes = []

            segments = []

            segment_start = 0
            previous_date_obj = None

            for date in sorted(self.quotes):

                if date < start_date:
                    continue

                if date >= end_date:
                    break

                date_obj = datetime.strptime(date, "%Y%m%d").date()

                if date_obj.weekday() > 4:
                    continue

                quotes = self.quotes[date][stock]


                # --------------------------------------------------------
                # START NEW SEGMENT AFTER WEEKENDS / MISSING DATES
                # --------------------------------------------------------

                if previous_date_obj is not None and (date_obj - previous_date_obj).days > 1:

                    if len(opens) > segment_start:
                        segments.append((segment_start, len(opens)))

                    segment_start = len(opens)


                # --------------------------------------------------------
                # STORE ORIGINAL CANDLES
                # --------------------------------------------------------

                for candle_i in range(4, 1334):

                    candle = quotes[candle_i]

                    dates.append(date)
                    candle_indices.append(candle_i)

                    opens.append(candle[0])
                    highs.append(candle[1])
                    lows.append(candle[2])
                    closes.append(candle[3])

                previous_date_obj = date_obj


            # Final segment
            if len(opens) > segment_start:
                segments.append((segment_start, len(opens)))


            self._breakout_flat_cache[cache_key] = {
                "dates": dates,
                "indices": candle_indices,
                "opens": opens,
                "highs": highs,
                "lows": lows,
                "closes": closes,
                "segments": segments,

                # Rolling breakout ranges will also be cached by n
                "rolling_cache": {}
            }


        # ================================================================
        # GET CACHED FLATTENED DATA
        # ================================================================

        market_data = self._breakout_flat_cache[cache_key]

        dates = market_data["dates"]
        candle_indices = market_data["indices"]

        opens = market_data["opens"]
        highs = market_data["highs"]
        lows = market_data["lows"]
        closes = market_data["closes"]

        segments = market_data["segments"]


        # ================================================================
        # PRECOMPUTE PREVIOUS N-CANDLE HIGH / LOW
        #
        # Uses monotonic deques.
        #
        # Complexity:
        #
        # Old:
        #     approximately O(candles * n)
        #
        # New:
        #     O(candles)
        #
        # Each candle enters and leaves each deque at most once.
        # ================================================================

        rolling_cache = market_data["rolling_cache"]

        if n not in rolling_cache:

            previous_highs = [None] * len(opens)
            previous_lows = [None] * len(opens)


            for segment_start, segment_end in segments:

                high_queue = deque()
                low_queue = deque()


                for k in range(segment_start, segment_end):

                    # ----------------------------------------------------
                    # REMOVE CANDLES OLDER THAN N
                    # ----------------------------------------------------

                    oldest_allowed = k - n

                    while high_queue and high_queue[0] < oldest_allowed:
                        high_queue.popleft()

                    while low_queue and low_queue[0] < oldest_allowed:
                        low_queue.popleft()


                    # ----------------------------------------------------
                    # RANGE CONTAINS PREVIOUS N CANDLES ONLY
                    #
                    # Current candle k has NOT yet been added.
                    # ----------------------------------------------------

                    if k - segment_start >= n:

                        previous_highs[k] = highs[high_queue[0]]
                        previous_lows[k] = lows[low_queue[0]]


                    # ----------------------------------------------------
                    # ADD CURRENT HIGH TO MONOTONIC MAX QUEUE
                    # ----------------------------------------------------

                    while high_queue and highs[high_queue[-1]] <= highs[k]:
                        high_queue.pop()

                    high_queue.append(k)


                    # ----------------------------------------------------
                    # ADD CURRENT LOW TO MONOTONIC MIN QUEUE
                    # ----------------------------------------------------

                    while low_queue and lows[low_queue[-1]] >= lows[k]:
                        low_queue.pop()

                    low_queue.append(k)


            rolling_cache[n] = (
                previous_highs,
                previous_lows
            )


        # ================================================================
        # GET CACHED BREAKOUT RANGES
        # ================================================================

        previous_highs, previous_lows = rolling_cache[n]


        # ================================================================
        # RUN STRATEGY
        # ================================================================

        for segment_start, segment_end in segments:

            k = segment_start + n


            while k < segment_end:

                # Need m future candles inside same segment
                if k + m >= segment_end:
                    break


                # ========================================================
                # ENTRY WINDOW
                #
                # candle_i is the ORIGINAL self.quotes index.
                # ========================================================

                signal_i = candle_indices[k]

                if signal_i < entry_i_start or signal_i > entry_i_end:
                    k += 1
                    continue


                signal_date = dates[k]

                current_price = opens[k]

                previous_high = previous_highs[k]
                previous_low = previous_lows[k]


                # ========================================================
                # DAILY ENTRY COUNTS
                # ========================================================

                long_count = long_entries_per_day.get(signal_date, 0)
                short_count = short_entries_per_day.get(signal_date, 0)


                # ========================================================
                # LONG BREAKOUT
                # ========================================================

                if current_price > previous_high and long_count < max_long_entries_per_day:

                    entry_price = current_price

                    stop_price = entry_price * (1 - stop_loss_pct)
                    take_profit_price = entry_price * (1 + take_profit_pct)

                    exit_price = None
                    exit_date = None
                    exit_i = None
                    exit_reason = None
                    exit_offset = m


                    # ----------------------------------------------------
                    # SEARCH FOR SL / TP
                    # ----------------------------------------------------

                    for offset in range(1, m + 1):

                        future_k = k + offset

                        candle_high = highs[future_k]
                        candle_low = lows[future_k]


                        # ------------------------------------------------
                        # STOP LOSS
                        #
                        # Pessimistic assumption if SL and TP both occur
                        # in the same candle: SL happens first.
                        # ------------------------------------------------

                        if candle_low <= stop_price:

                            exit_price = stop_price - slippage

                            exit_date = dates[future_k]
                            exit_i = candle_indices[future_k]

                            exit_reason = "SL"
                            exit_offset = offset

                            long_stop_count += 1

                            break


                        # ------------------------------------------------
                        # TAKE PROFIT
                        # ------------------------------------------------

                        elif candle_high >= take_profit_price:

                            exit_price = take_profit_price - slippage

                            exit_date = dates[future_k]
                            exit_i = candle_indices[future_k]

                            exit_reason = "TP"
                            exit_offset = offset

                            long_tp_count += 1

                            break


                    # ----------------------------------------------------
                    # TIMEOUT
                    # ----------------------------------------------------

                    if exit_price is None:

                        future_k = k + m

                        exit_price = opens[future_k] - slippage

                        exit_date = dates[future_k]
                        exit_i = candle_indices[future_k]

                        exit_reason = "TIMEOUT"
                        exit_offset = m

                        long_timeout_count += 1


                    # ----------------------------------------------------
                    # RETURN
                    # ----------------------------------------------------

                    raw_return = exit_price / entry_price - 1
                    leveraged_return = raw_return * leverage

                    long_raw_returns.append(raw_return)
                    long_returns.append(leveraged_return)

                    long_entries_per_day[signal_date] = long_count + 1


                    # ----------------------------------------------------
                    # COMPOUND BALANCE
                    # ----------------------------------------------------

                    balance_before = self.balance

                    self.balance *= 1 + leveraged_return
                    
                    
                    
                    self.equity_history.append(self.balance)
                    self.deposit_history.append(self.deposited)


                    # ----------------------------------------------------
                    # OPTIONAL DEBUG OUTPUT
                    # ----------------------------------------------------

                    if verbose:
                        print(
                            "LONG",
                            "entry:", signal_date, signal_i,
                            "exit:", exit_date, exit_i,
                            "entry #:", long_entries_per_day[signal_date],
                            "leverage:", leverage,
                            "entry price:", entry_price,
                            "SL:", round(stop_price, 2),
                            "TP:", round(take_profit_price, 2),
                            "exit price:", round(exit_price, 2),
                            "reason:", exit_reason,
                            "raw return:", round(raw_return * 100, 4), "%",
                            "leveraged return:", round(leveraged_return * 100, 4), "%",
                            "balance:", round(balance_before, 2),
                            "->", round(self.balance, 2)
                        )


                    # Continue from actual exit candle
                    k += exit_offset
                    continue


                # ========================================================
                # SHORT BREAKOUT
                # ========================================================

                elif not LONG_ONLY and current_price < previous_low and short_count < max_short_entries_per_day:

                    entry_price = current_price

                    stop_price = entry_price * (1 + stop_loss_pct)
                    take_profit_price = entry_price * (1 - take_profit_pct)

                    exit_price = None
                    exit_date = None
                    exit_i = None
                    exit_reason = None
                    exit_offset = m


                    # ----------------------------------------------------
                    # SEARCH FOR SL / TP
                    # ----------------------------------------------------

                    for offset in range(1, m + 1):

                        future_k = k + offset

                        candle_high = highs[future_k]
                        candle_low = lows[future_k]


                        # ------------------------------------------------
                        # STOP LOSS
                        # ------------------------------------------------

                        if candle_high >= stop_price:

                            exit_price = stop_price + slippage

                            exit_date = dates[future_k]
                            exit_i = candle_indices[future_k]

                            exit_reason = "SL"
                            exit_offset = offset

                            short_stop_count += 1

                            break


                        # ------------------------------------------------
                        # TAKE PROFIT
                        # ------------------------------------------------

                        elif candle_low <= take_profit_price:

                            exit_price = take_profit_price + slippage

                            exit_date = dates[future_k]
                            exit_i = candle_indices[future_k]

                            exit_reason = "TP"
                            exit_offset = offset

                            short_tp_count += 1

                            break


                    # ----------------------------------------------------
                    # TIMEOUT
                    # ----------------------------------------------------

                    if exit_price is None:

                        future_k = k + m

                        exit_price = opens[future_k] + slippage

                        exit_date = dates[future_k]
                        exit_i = candle_indices[future_k]

                        exit_reason = "TIMEOUT"
                        exit_offset = m

                        short_timeout_count += 1


                    # ----------------------------------------------------
                    # RETURN
                    # ----------------------------------------------------

                    raw_return = (entry_price - exit_price) / entry_price
                    leveraged_return = raw_return * leverage

                    short_raw_returns.append(raw_return)
                    short_returns.append(leveraged_return)

                    short_entries_per_day[signal_date] = short_count + 1


                    # ----------------------------------------------------
                    # COMPOUND BALANCE
                    # ----------------------------------------------------

                    balance_before = self.balance

                    self.balance *= 1 + leveraged_return


                    # ----------------------------------------------------
                    # OPTIONAL DEBUG OUTPUT
                    # ----------------------------------------------------

                    if verbose:
                        print(
                            "SHORT",
                            "entry:", signal_date, signal_i,
                            "exit:", exit_date, exit_i,
                            "entry #:", short_entries_per_day[signal_date],
                            "leverage:", leverage,
                            "entry price:", entry_price,
                            "SL:", round(stop_price, 2),
                            "TP:", round(take_profit_price, 2),
                            "exit price:", round(exit_price, 2),
                            "reason:", exit_reason,
                            "raw return:", round(raw_return * 100, 4), "%",
                            "leveraged return:", round(leveraged_return * 100, 4), "%",
                            "balance:", round(balance_before, 2),
                            "->", round(self.balance, 2)
                        )


                    # Continue from actual exit
                    k += exit_offset
                    continue


                # No trade
                k += 1


        # ================================================================
        # OVERALL STATISTICS
        # ================================================================

        all_returns = long_returns + short_returns
        all_raw_returns = long_raw_returns + short_raw_returns

        avg_long_return = sum(long_returns) / len(long_returns) if long_returns else 0
        avg_short_return = sum(short_returns) / len(short_returns) if short_returns else 0
        avg_trade_return = sum(all_returns) / len(all_returns) if all_returns else 0

        avg_long_raw_return = sum(long_raw_returns) / len(long_raw_returns) if long_raw_returns else 0
        avg_short_raw_return = sum(short_raw_returns) / len(short_raw_returns) if short_raw_returns else 0
        avg_raw_return = sum(all_raw_returns) / len(all_raw_returns) if all_raw_returns else 0

        long_winners = sum(1 for r in long_returns if r > 0)
        short_winners = sum(1 for r in short_returns if r > 0)
        total_winners = sum(1 for r in all_returns if r > 0)

        long_win_rate = long_winners / len(long_returns) if long_returns else 0
        short_win_rate = short_winners / len(short_returns) if short_returns else 0
        total_win_rate = total_winners / len(all_returns) if all_returns else 0


        # ================================================================
        # OVERALL SUMMARY ONLY
        # ================================================================

        print()
        print("============================================================")
        print("BREAKOUT STRATEGY - OVERALL RESULTS")
        print("============================================================")

        print("Breakout lookback:", n, "candles")
        print("Entry i range:", entry_i_start, "-", entry_i_end)
        print("Timeout:", m, "candles")
        print("Leverage:", leverage, "x")
        print("Stop loss:", round(stop_loss_pct * 100, 4), "%")
        print("Take profit:", round(take_profit_pct * 100, 4), "%")
        print("Slippage:", slippage, "points")

        print()

        print("Long trades:", len(long_returns))
        print("Long TP:", long_tp_count)
        print("Long SL:", long_stop_count)
        print("Long timeout:", long_timeout_count)
        print("Average long raw return:", round(avg_long_raw_return * 100, 6), "%")
        print("Average long leveraged return:", round(avg_long_return * 100, 6), "%")
        print("Long win rate:", round(long_win_rate * 100, 2), "%")

        print()

        print("Short trades:", len(short_returns))
        print("Short TP:", short_tp_count)
        print("Short SL:", short_stop_count)
        print("Short timeout:", short_timeout_count)
        print("Average short raw return:", round(avg_short_raw_return * 100, 6), "%")
        print("Average short leveraged return:", round(avg_short_return * 100, 6), "%")
        print("Short win rate:", round(short_win_rate * 100, 2), "%")

        print()

        print("Total trades:", len(all_returns))
        print("Total TP:", long_tp_count + short_tp_count)
        print("Total SL:", long_stop_count + short_stop_count)
        print("Total timeout:", long_timeout_count + short_timeout_count)
        print("Average raw return:", round(avg_raw_return * 100, 6), "%")
        print("Average leveraged return:", round(avg_trade_return * 100, 6), "%")
        print("Overall win rate:", round(total_win_rate * 100, 2), "%")
        print("Final balance:", round(self.balance, 2))

        print("============================================================")
        
        if(plot is True):
            plotting(self.equity_history, self.deposit_history)
            
if __name__ == "__main__":
    files = os.listdir()

    sim = Sim()
    
    #sim.read_quotes(files, "20220103")
    sim.quotes = sim.load_quotes("quotes.pkl")
    if(len(sim.quotes) == 0):
        #sim.read_quotes(files, "20180413")
        sim.read_csv_quotes(files, "20180413")
    
    LEVERAGE = 3
    SL = (100-50/LEVERAGE)/100
    BE = 0.996
    sim_i = Sim()
    
    tpps = [0.007,0.02,0.05,0.05,0.05]
    sim.process(sim_i.quotes, "QQQ","20220103", "20260804", 10000, 800, 300, 0.10, 0.005, 8, True, True)