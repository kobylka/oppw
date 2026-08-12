from datetime import datetime, timedelta
import argparse
import os
import matplotlib.pyplot as plt
import numpy as np
import math
import random
import pickle
from pathlib import Path

from oppw_loss_control import (
        LOSS_CONTROL_DEFER_TUESDAY,
        LOSS_CONTROL_ENTER,
        arithmetic_loss_control_trigger,
        loss_control_entry_decision,
        normalized_tuesday_reentry,
        premarket_closes_near_low,
)

def add_days(date, D):
        date_obj = datetime.strptime(date, "%Y%m%d")
        new_date = date_obj + timedelta(days=D)
        new_date = new_date.strftime("%Y%m%d")
        return new_date
        
def date_diff(date_str1, date_str2):
        # Convert the date strings to datetime objects
        date1 = datetime.strptime(date_str1, '%Y%m%d')
        date2 = datetime.strptime(date_str2, '%Y%m%d')

        # Calculate the difference in days
        return (date2 - date1).days

def weekly_trading_day_indices(quote_dates):
        """Return each quote date's zero-based trading-session index in its ISO week."""
        indices = {}
        session_counts = {}

        for date in sorted(quote_dates):
                date_obj = datetime.strptime(date, "%Y%m%d").date()

                if date_obj.weekday() > 4:
                        continue

                iso_year, iso_week, _ = date_obj.isocalendar()
                week_key = (iso_year, iso_week)
                session_index = session_counts.get(week_key, 0)
                indices[date] = session_index
                session_counts[week_key] = session_index + 1

        return indices

def interpolated_premarket_tpp(
        start_tpp,
        end_tpp,
        bar_index,
        first_bar_index=4,
        cash_open_index=934,
):
        """Linearly scale TPP from midnight to the cash-session open."""
        interval = cash_open_index - first_bar_index

        if interval <= 0:
                raise ValueError("cash_open_index must be greater than first_bar_index")

        progress = (bar_index - first_bar_index) / interval
        progress = min(max(progress, 0.0), 1.0)
        return start_tpp + (end_tpp - start_tpp) * progress

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
        self.week_no=0
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
        self.loss_control_lookback = None
        self.loss_control_outcomes = []
        self.loss_control_events = []
        self.leverage_override = False

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
                    self.wallet[stock] = [0, 0, 0, 0]
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
                    
                    if(date not in self.quotes):
                        continue
                    
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
            
    def read_quotes(self, files, start_date):
        for f in files:
            fname = f.split(".")
            if fname[-1] == "txt" and fname[0] != "weekly_returns":
                stock = fname[0].upper()
                self.stocks.append(stock)
                self.wallet[stock] = [0,0,0,0]
            else :
                continue
            
            with open(f) as lines:
                init = False
                for line in lines:
                    line = line.split(",")
                    if line[0] == "<TICKER>":
                        continue

                    date = line[2]
                    
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
                    elif init is False:
                        continue
                        
                    if init is True:
                        opon = float(line[4])
                        high = float(line[5])
                        low = float(line[6])
                        close = float(line[7])
                        
                        if date not in self.quotes:
                            self.quotes[date] = {}

                        self.quotes[date][stock] = [opon, high, low, close]
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

    def sell(self, time, open_price, close_price, open_date, close_date, trade_type, LEVERAGE, debug=False):
                SL =  (100-50/LEVERAGE)/100
                #SL = 0.9375
                
                if self.leverage_override:
                    granular = int((self.balance/1.765/2240))*2240
                else:
                    granular = int((self.balance/(20/LEVERAGE)/2240))*2240
                #granular = int((self.balance/(20/LEVERAGE)/2240)+1)*2240
                #if(round(20/(self.balance/granular), 2) < 3):
                #    granular = int((self.balance/(20/LEVERAGE)/2240)+2)*2240
                #if(round(20/(self.balance/granular), 2) < 3):
                 #   granular = int((self.balance/(20/LEVERAGE)/2240)+3)*2240
                #if(LEVERAGE == 10):
                    #granular = int((self.balance/1.765/2240))*2240
                    
                effective_leverage = round(20/(self.balance/granular), 2)
                    
                #change = round(close_price/open_price-1,4)
                change = int((close_price/open_price-1)*100000)/100000
                if self.loss_control_lookback is not None:
                    self.loss_control_outcomes.append(change)
                    self.loss_control_events.append({
                        "date": open_date,
                        "action": "TRADE",
                        "outcome": change,
                    })
                #print(LEVERAGE, self.balance, change)
                #print(change)
                self.cumulative_change *= change*LEVERAGE+1
                lev = LEVERAGE
                #if(self.prev_change < -0.02):
                #    lev = 6
                #if(max_equity > 0):
                #    if(balance/max_equity > 0.6):
                #        lev = 6
                
                trade_return = (granular*20*change)/self.balance
                
                self.trade_returns.append(float(trade_return))
                
                self.gained += granular*20*change
                self.balance += granular*20*change
                
                trade_period = date_diff(open_date, close_date)+1
                if(trade_period > 5): trade_period = 5
                
                self.days_in_position += trade_period
                
                if(change < 0):
                    self.loses.append(change*LEVERAGE)
                else:
                    self.wins.append(change*LEVERAGE)
                    
                
                ratio = round(len(self.wins)/(len(self.wins)+len(self.loses)),4)
                
                if(len(self.wins) > 0):
                    avg_win  = round(sum(self.wins) / len(self.wins),3)
                else:
                    avg_win = 0
                    
                if(len(self.loses) > 0):
                    avg_loss = round(sum(self.loses) / len(self.loses),3)
                else:
                    avg_loss = 0
                
                
                if(debug == True):
                    #print(self.balance)
                    print(effective_leverage, granular, self.balance,self.trade_no, time,trade_type, open_date, close_date, date_diff(open_date, close_date)+1, change, math.pow(self.balance/self.deposited, 1/self.trade_no), ratio, avg_loss, avg_win)
                if(change*lev < -0.1): self.lost += granular*20**lev
                
                if(self.balance > self.max_equity):
                    if(self.n > 2):
                        self.dd += self.n
                        #if(debug is True): print(date,n,round(100*(local_dd_equity/max_equity-1),3))
                        
                    self.max_equity = self.balance
                    self.local_dd_equity = 1000000000000
                    self.n = 0
                else:
                    local_dd = self.balance / self.max_equity
                    if(local_dd < self.max_dd):
                        self.max_dd = local_dd
                    if(self.balance < self.local_dd_equity):
                        self.local_dd_equity = self.balance
                    self.n+=1
                #print(date,round(100*(self.balance/self.max_equity-1),3))
                self.prev_change = change
                self.break_even = False
                
                self.returns.append(change*LEVERAGE)
                
                if(change < -0.0041):
                    self.classD += 1
                elif(change < 0):
                    self.classC += 1
                elif(change < 0.007):
                    self.classB += 1
                else:
                    self.classA += 1
                    
                if(self.balance >= self.max_equity):
                    if(self.dd_current_duration > self.max_dd_duration):
                        self.max_dd_duration = self.dd_current_duration
                    if(self.dd_current_duration > 2):
                        self.dd_total_duration += self.dd_current_duration
                    self.dd_current_duration = 0
                else:
                    self.dd_current_duration += 1
                    
                self.equity_history.append(self.balance)
                self.deposit_history.append(self.deposited)
    
    def process(
        self,
        quotes,
        stock,
        start_date,
        end_date,
        leverage,
        tpps,
        disaster_stop_ratio,
        BE,
        thursday_stop,
        friday_stop,
        initial_balance=12000.0,
        allow_deposits=False,
        apply_tax=False,
        debug=False,
        plots=False,
        loss_control_lookback=None,
        loss_control_threshold=0.02,
        opening_gap_threshold=0.01,
        momentum20_threshold=-0.005,
        tuesday_normalization_tolerance=0.005,
        premarket_low_enabled=False,
        premarket_minimum_range=0.008,
        premarket_maximum_close_location=0.15,
        arithmetic_loss_control_enabled=None,
        gap_momentum_enabled=None,
        tuesday_normalization_enabled=None,
        premarket_range_enabled=None,
        premarket_close_near_low_enabled=None,
        leverage_override=False,
    ):
        legacy_loss_controls = loss_control_lookback is not None
        arithmetic_loss_control_enabled = (
            legacy_loss_controls
            if arithmetic_loss_control_enabled is None
            else bool(arithmetic_loss_control_enabled)
        )
        gap_momentum_enabled = (
            legacy_loss_controls
            if gap_momentum_enabled is None
            else bool(gap_momentum_enabled)
        )
        tuesday_normalization_enabled = (
            legacy_loss_controls
            if tuesday_normalization_enabled is None
            else bool(tuesday_normalization_enabled)
        )
        premarket_range_enabled = (
            premarket_low_enabled
            if premarket_range_enabled is None
            else bool(premarket_range_enabled)
        )
        premarket_close_near_low_enabled = (
            premarket_low_enabled
            if premarket_close_near_low_enabled is None
            else bool(premarket_close_near_low_enabled)
        )
        premarket_low_enabled = (
            premarket_range_enabled and premarket_close_near_low_enabled
        )
        if arithmetic_loss_control_enabled and loss_control_lookback is None:
            loss_control_lookback = 2

        self.trade_returns = []
        self.daily_equity_points = []
        self.leverage = leverage
        self.loss_control_lookback = loss_control_lookback
        self.loss_control_outcomes = []
        self.loss_control_events = []
        self.leverage_override = leverage_override
        
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
        self.week_no=0
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
            
        thursday_SL = 1-thursday_stop
        friday_SL = 1-friday_stop

        # TPP levels follow the order of actual trading sessions in each ISO
        # week. For example, when Monday is absent, Tuesday receives tpps[0],
        # Wednesday tpps[1], and subsequent sessions advance from there.
        trading_day_indices = weekly_trading_day_indices(self.quotes.keys())
        quote_dates = sorted(self.quotes)
        quote_positions = {quote_date: index for index, quote_date in enumerate(quote_dates)}
        pending_tuesday_reentry = False
        pending_friday_close = 0.0
        pending_monday_date = ""

        if arithmetic_loss_control_enabled:
            arithmetic_loss_control_trigger(
                [],
                loss_control_lookback,
                loss_control_threshold,
            )
        
        z = 0
        
        for date in quote_dates:
            if date < start_date: continue
            if date >= end_date: break

            date_obj = datetime.strptime(date, "%Y%m%d").date()
            weekday_index = date_obj.weekday()

            if weekday_index > 4: continue

            is_monday = weekday_index == 0
            is_tuesday = weekday_index == 1
            is_wednesday = weekday_index == 2
            is_thursday = weekday_index == 3
            is_friday = weekday_index == 4

            quotes = self.quotes[date][stock]

            qqq_open = quotes[0]
            qqq_close = quotes[3]
            
            openest = quotes[4][0]
            opon = quotes[934][0]
            close = quotes[1324][3]

            trading_day_index = trading_day_indices[date]
            tpp = tpps[min(trading_day_index, len(tpps) - 1)]

            close_price = 0
            close_date = date
            trade_type = ""
            i = 1324

            new_week_entry = (date_diff(prev_date, date) > 1 and weekday_index in (0, 1))

            # --------------------------------------------------------
            # Close previous position at the previous session close.
            # This must happen before yearly accounting and sizing.
            # --------------------------------------------------------
            
            #if new_week_entry:
            #    if(self.prev_full_week_change < -0.02 or self.prev_change < -0.007):
            #        self.leverage += 1
            #    else:
            #        self.leverage = 6
            #    
            #    if(self.max_equity > 0):
            #        if(self.balance/self.max_equity < 0.99 and self.leverage == 3):
            #            self.leverage = 4

            if new_week_entry and open_price > 0:
                close_date = prev_date
                close_price = self.quotes[prev_date][stock][i][3]
                trade_type = "TO"

                self.sell(i,open_price,close_price,open_date,close_date,trade_type,LEVERAGE,debug)

                open_price = 0
                close_price = 0
                qqq_open_price = 0
                open_date = ""

                close_date = date
                trade_type = ""

            # --------------------------------------------------------
            # Yearly accounting after any previous-session exit.
            # --------------------------------------------------------

            if (prev_year[:4] != date[:4] and self.balance > 0 and open_price == 0):
                yearlies.append(round(100 * (self.balance / prev_equity - 1), 1))

                prev_year = date
                prev_equity = self.balance

                tax = self.gained * 0.19

                if tax > 0 and apply_tax:
                    #print()
                    #print(date)
                    #print(self.balance)
                    #print(tax)
                    self.balance -= tax
                    self.gained = 0
                    #print(self.balance)
                    #print()

            # --------------------------------------------------------
            # Calculate leverage, stop and sizing after the exit.
            # --------------------------------------------------------

            if (self.prev_full_week_change < -0.02 or self.prev_change < -0.007) and self.leverage == 8:
                LEVERAGE = 10
            else:
                LEVERAGE = self.leverage
            
            if(self.prev_open > 0):
                current_week_change = close/self.prev_open-1
                if(is_thursday and add_days(date,1) not in self.quotes):
                    self.prev_full_week_change = current_week_change
                elif(is_friday):
                    self.prev_full_week_change = current_week_change
                elif(is_wednesday and add_days(date,1) not in self.quotes and add_days(date,2) not in self.quotes):
                    self.prev_full_week_change = current_week_change

            SL = (100 - 50 / LEVERAGE) / 100
            #SL = 0.9375

            if self.leverage_override:
                granular = int((self.balance/1.765/2240))*2240
            else:
                granular = int(self.balance / (20 / LEVERAGE) / 2240) * 2240
                granular *= 20 / LEVERAGE

            if granular == 0 and self.balance < initial_balance:
                deposit = initial_balance - self.balance
                self.deposited += deposit
                self.balance += deposit

            # --------------------------------------------------------
            # Premarket processing for an existing carried position.
            # A new weekly position has not been opened yet.
            # --------------------------------------------------------

            if open_price > 0:
                if open_price * SL > openest:
                    i = 4
                    close_date = date
                    close_price = openest
                    trade_type = "GAP DOWN"

            if close_price == 0 and open_price > 0:
                for i in range(4, 934):
                    o = quotes[i][0]
                    l = quotes[i][2]

                    if open_price * SL > o:
                        close_date = date
                        close_price = o
                        trade_type = "SLPRE"
                        break

                    elif open_price * SL > l:
                        close_date = date
                        close_price = l
                        trade_type = "SLPRE"
                        break

                    elif is_thursday and o / open_price < thursday_SL:
                        close_date = date
                        close_price = o
                        trade_type = "TSL1PRE"
                        break
                        
                    elif (self.break_even and o > open_price * BE):
                        close_date = date
                        close_price = o
                        trade_type = "BEPRE"
                        break
                    elif(
                        trading_day_index == 1
                        and (is_tuesday or is_wednesday)
                        and date_diff(open_date, date) == 1
                    ):
                        premarket_tpp = interpolated_premarket_tpp(
                            tpps[0],
                            tpps[1],
                            i,
                        )
                        if(o > open_price * (1 + premarket_tpp)):
                            close_date = date
                            close_price = o
                            trade_type = "PREOH"
                            break


            if close_price > 0 and open_price > 0:
                self.sell(i,open_price,close_price,open_date,close_date,trade_type,LEVERAGE,debug)

                open_price = 0
                close_price = 0
                qqq_open_price = 0
                open_date = ""

            # --------------------------------------------------------
            # Open the new weekly position at the cash-session open.
            # --------------------------------------------------------

            should_open_week = False

            if (
                gap_momentum_enabled
                and pending_tuesday_reentry
                and date != pending_monday_date
                and open_price == 0
            ):
                pending_tuesday_reentry = False
                normalized = (
                    not tuesday_normalization_enabled
                    or normalized_tuesday_reentry(
                        pending_friday_close,
                        qqq_open,
                        tuesday_normalization_tolerance,
                    )
                )
                if is_tuesday and normalized:
                    should_open_week = True
                    self.loss_control_events.append({
                        "date": date,
                        "action": "TUESDAY_REENTRY",
                        "friday_close": pending_friday_close,
                        "tuesday_open": qqq_open,
                    })
                else:
                    if arithmetic_loss_control_enabled:
                        self.loss_control_outcomes.append(0.0)
                    self.loss_control_events.append({
                        "date": date,
                        "action": "SKIP_TUESDAY_NOT_NORMALIZED",
                        "friday_close": pending_friday_close,
                        "tuesday_open": qqq_open,
                    })
                pending_friday_close = 0.0
                pending_monday_date = ""

            elif new_week_entry and open_price == 0:
                self.week_no += 1
                if not (
                    arithmetic_loss_control_enabled
                    or gap_momentum_enabled
                    or premarket_low_enabled
                ):
                    should_open_week = True
                else:
                    quote_index = quote_positions[date]
                    previous_index = quote_index - 1
                    previous_cash_close = 0.0
                    previous_daily_close = 0.0
                    momentum20 = None
                    premarket_range = None
                    premarket_close_location = None
                    premarket_low = False

                    if previous_index >= 0:
                        previous_date = quote_dates[previous_index]
                        previous_quotes = self.quotes[previous_date][stock]
                        previous_cash_close = previous_quotes[1324][3]
                        previous_daily_close = previous_quotes[3]

                    if previous_index >= 20:
                        momentum_base_date = quote_dates[previous_index - 20]
                        momentum_base_close = self.quotes[momentum_base_date][stock][3]
                        momentum20 = previous_daily_close / momentum_base_close - 1.0

                    if premarket_low_enabled:
                        premarket_quotes = quotes[4:934]
                        premarket_open = premarket_quotes[0][0]
                        premarket_high = max(
                            quote[1] for quote in premarket_quotes
                        )
                        premarket_low_price = min(
                            quote[2] for quote in premarket_quotes
                        )
                        premarket_close = premarket_quotes[-1][3]
                        premarket_span = premarket_high - premarket_low_price
                        if premarket_open > 0:
                            premarket_range = premarket_span / premarket_open
                        if premarket_span > 0:
                            premarket_close_location = (
                                (premarket_close - premarket_low_price)
                                / premarket_span
                            )
                        premarket_low = premarket_closes_near_low(
                            premarket_open,
                            premarket_high,
                            premarket_low_price,
                            premarket_close,
                            premarket_minimum_range,
                            premarket_maximum_close_location,
                        )

                    entry_decision = loss_control_entry_decision(
                        self.loss_control_outcomes,
                        loss_control_lookback,
                        opon,
                        previous_cash_close,
                        momentum20,
                        is_monday,
                        loss_control_threshold,
                        opening_gap_threshold,
                        momentum20_threshold,
                        premarket_low,
                        gap_momentum_enabled=gap_momentum_enabled,
                    )

                    if entry_decision == LOSS_CONTROL_ENTER:
                        should_open_week = True
                    elif entry_decision == LOSS_CONTROL_DEFER_TUESDAY:
                        pending_tuesday_reentry = True
                        pending_friday_close = previous_daily_close
                        pending_monday_date = date
                        self.loss_control_events.append({
                            "date": date,
                            "action": LOSS_CONTROL_DEFER_TUESDAY,
                            "gap": opon / previous_cash_close - 1.0,
                            "momentum20": momentum20,
                        })
                    else:
                        if arithmetic_loss_control_enabled:
                            self.loss_control_outcomes.append(0.0)
                        self.loss_control_events.append({
                            "date": date,
                            "action": entry_decision,
                            "gap": (
                                opon / previous_cash_close - 1.0
                                if previous_cash_close > 0
                                else None
                            ),
                            "momentum20": momentum20,
                            "premarket_range": premarket_range,
                            "premarket_close_location": premarket_close_location,
                        })

            if should_open_week and open_price == 0:
                open_price = opon
                self.prev_open = opon
                open_date = date
                qqq_open_price = qqq_open
                self.trade_no += 1
                
                #if(self.deposited < 200000 and  self.max_equity > 0):
                #    if self.balance/self.max_equity < 0.95:
                #        self.deposited += 3000
                #        self.balance += 3000
                if(self.deposited < 200000 and (self.prev_full_week_change < -0.02 or self.prev_change < -0.007)):
                    granular = int((self.balance/1.765/2240))
                    plus_one = int(2240*(granular+1)*1.765-self.balance+200)
                    self.deposited += plus_one
                    self.balance += plus_one
                    
                z += 1
            # --------------------------------------------------------
            # Cash-open exits.
            # --------------------------------------------------------

            i = 934

            if open_price > 0:
                if open_price * SL > opon:
                    close_date = date
                    close_price = opon
                    trade_type = "SLO"

                elif opon > open_price * (1 + tpp):
                    close_date = date
                    close_price = opon
                    trade_type = "OH"

                elif (self.break_even and opon > open_price * BE):
                    close_date = date
                    close_price = opon
                    trade_type = "BEO"

                elif (is_thursday and opon / open_price < thursday_SL):
                    close_date = date
                    close_price = opon
                    trade_type = "TSL1"

                elif (is_friday and opon / open_price < friday_SL):
                    close_date = date
                    close_price = opon
                    trade_type = "TSL3"

            # --------------------------------------------------------
            # Regular-session minute processing.
            # --------------------------------------------------------

            if close_price == 0 and open_price > 0:
                for i in range(934, 1325):
                    o = quotes[i][0]
                    h = quotes[i][1]
                    l = quotes[i][2]

                    #if(i==944 and date_diff(date,open_date) == 0):
                    #    if(o/open_price < 0.994):
                    #        close_date = date
                    #        close_price = o
                    #        trade_type = "FUCKTHIS"
                    #        break

                    if open_price * SL > o:
                        close_date = date
                        close_price = o
                        trade_type = "SL"
                        break

                    elif open_price * SL > l:
                        close_date = date
                        close_price = l
                        trade_type = "SL"
                        break

                    elif (is_thursday and l / open_price < thursday_SL):
                        close_date = date
                        close_price = open_price * thursday_SL
                        trade_type = "TSL2"
                        break

                    elif (is_friday and l / open_price < friday_SL):
                        close_date = date
                        close_price = open_price * friday_SL
                        trade_type = "TSL4"
                        break

                    elif (self.break_even and h > open_price * BE):
                        close_date = date
                        close_price = open_price * BE
                        trade_type = "BH"
                        break

            # --------------------------------------------------------
            # Close-based exits.
            # --------------------------------------------------------

            if open_price > 0 and close_price == 0:
                if close > open_price * (1 + tpp):
                    i = 1324
                    close_date = date
                    close_price = close
                    trade_type = "CH"
                    
                #elif (is_wednesday and (close+1) / open_price < thursday_SL):
                elif (is_wednesday and (close+100000) / open_price < thursday_SL):
                    i = 1324
                    close_date = date
                    close_price = close
                    trade_type = "TSL0"

                elif is_friday:
                    i = 1324
                    close_date = date
                    close_price = close
                    trade_type = "TO"

            # --------------------------------------------------------
            # Execute selected exit.
            # --------------------------------------------------------

            if close_price > 0 and open_price > 0:
                self.sell(i, open_price,close_price,open_date,close_date,trade_type,LEVERAGE,debug)

                open_price = 0
                close_price = 0
                qqq_open_price = 0
                open_date = ""

            # --------------------------------------------------------
            # Update state only for a position surviving the day.
            # --------------------------------------------------------

            if (open_price > 0 and qqq_close < qqq_open_price * BE and self.break_even is False):
                if(date_diff(open_date, date) == 0):
                    #holiday
                    holiday = 1
                    #print(date_diff(open_date, date))
                else:
                    self.break_even = True

            if open_price > 0:
                current_change = close / open_price - 1.0

                marked_equity = self.balance * (1.0 + current_change * LEVERAGE)
            else:
                marked_equity = self.balance

            prev_date = date

            self.daily_equity_points.append((date, float(marked_equity)))
            
        self.dd_total_duration += self.dd_current_duration
        self.dd_current_duration = 0
        
        yearlies.append(round(100 * (self.balance / prev_equity - 1), 1))
        
        print(yearlies)
        print(self.classA, self.classB, self.classC, self.classD)
        #print(TP, int(self.deposited),int(self.balance),round(self.lost/self.balance,3),self.dd)
        #print(start_date, end_date, self.classA, self.classB, self.classC, self.classD, self.cumulative_change, end=" ")
        #print(self.balance, self.max_equity, round(self.balance/self.max_equity, 4), self.deposited)

        #print_wallet(end_date, round(WIN/(WIN+LOSS), 2), 100*(1-MAX_DD),debug,MAX_EQUITY,WIN_AMOUNT/LOSS_AMOUNT,TIMEOUT,SL)
        if(plots == True):
            plotting(self.equity_history, self.deposit_history)        
        
        #return build_backtest_result(initial_balance=initial_balance, final_balance=self.balance, deposited=self.deposited, 
        #    trade_returns=self.trade_returns, days_in_position=self.days_in_position, start_date=start_date, end_date=end_date)
        
        total_cagr = round(self.balance/self.deposited, 2)
        years = (self.week_no*7)/365
        cagr = round(pow(total_cagr, 1/years), 2)
        
        return [int(self.balance), int(self.deposited), total_cagr, cagr,self.days_in_position,round(1-self.max_dd,3),self.max_dd_duration,self.dd_total_duration]
        
def bench_weeks(weeks, sim, LEVERAGE, SL, BE):
    start_date = ""
    end_date = "20260804"
    for date in sim.quotes:
        start_date = date
        break
      
    for i in range(0,200000):
        sim_i = Sim()
        sim_i.quotes = sim.quotes.copy()
        date = add_days(start_date, 7*i)
        end_date = add_days(date, 7*weeks)
        if(date not in sim.quotes):
            date = add_days(date, 1)
            if(date not in sim.quotes):
                date = add_days(date, 1)
                if(date not in sim.quotes):
                    date = add_days(date, 1)
                    if(date not in sim.quotes and date != "20010914" and date != "20200316" and date != "20200320"):
                        print(date, end_date)
                        break
        if(end_date not in sim.quotes):
            end_date = add_days(end_date, -1)
            if(end_date not in sim.quotes):
                end_date = add_days(end_date, -1)
                if(end_date not in sim.quotes):
                    end_date = add_days(end_date, -1)
                    if(end_date not in sim.quotes):
                        continue
        
        tpps = [0.007,0.02,0.05,0.05,0.05]
        result = sim.process(sim_i.quotes, "QQQ",date, end_date, LEVERAGE, tpps, SL, BE, 0.004,0.004, 30000, False,False,False,False)
        print(date, end_date, result)
def run_backtest(
    loss_control_lookback=None,
    debug=True,
    plots=True,
    premarket_low_enabled=False,
    arithmetic_loss_control_enabled=None,
    gap_momentum_enabled=None,
    tuesday_normalization_enabled=None,
    premarket_range_enabled=None,
    premarket_close_near_low_enabled=None,
    leverage_override=False,
):
    files = os.listdir()
    
    #start_date = "20181016"
    #start_date = "20000104"
    #start_date = "20000103"
    #start_date = "20100104"
    #start_date = "20220103"
    #start_date = "20150105"
    #start_date = "20220103"
    #start_date = "20240102"
    #start_date = "20220104"
    #start_date = "20210104"
    #start_date = "20100311"
    #start_date = "20180102"
    #end_date = "20230303"
    #end_date = "20081230"
    #end_date = "20100104"
    #end_date = "20240122"
    #end_date = "20200102"
    #end_date = "20160923"
    #end_date = "20251022"
    #end_date = "20160104"
    #end_date = "20190201"
    #end_date = "20230103"
    #end_date = "20200102"
    #end_date = "20120103"
    #end_date = "20111230"
    #end_date = "20191231"
    #end_date = "20221230"
    end_date = "20260706"
    
    sim = Sim()
    
    #sim.read_quotes(files, "20220103")
    sim.quotes = sim.load_quotes("quotes.pkl")
    if(len(sim.quotes) == 0):
        sim.read_quotes(files, "20180413")
        sim.read_csv_quotes(files, "20180413")
    
    LEVERAGE = 8
    SL = (100-50/LEVERAGE)/100
    BE = 0.996
    
    #bench_weeks(52, sim, LEVERAGE, SL, BE)
    
    sim_i = Sim()
    
    tpps = [0.007,0.02,0.05,0.05,0.05]
    print(tpps)
    result = sim.process(
        sim_i.quotes,
        "QQQ",
        "20250106",
        "20260804",
        LEVERAGE,
        tpps,
        SL,
        BE,
        0.004,
        0.004,
        initial_balance=16000,
        allow_deposits=False,
        apply_tax=True,
        debug=debug,
        plots=plots,
        loss_control_lookback=loss_control_lookback,
        premarket_low_enabled=premarket_low_enabled,
        arithmetic_loss_control_enabled=arithmetic_loss_control_enabled,
        gap_momentum_enabled=gap_momentum_enabled,
        tuesday_normalization_enabled=tuesday_normalization_enabled,
        premarket_range_enabled=premarket_range_enabled,
        premarket_close_near_low_enabled=premarket_close_near_low_enabled,
        leverage_override=leverage_override,
    )
    print(result)
    if loss_control_lookback is not None:
        print("loss-control lookback", loss_control_lookback)
        print("loss-control events", loss_control_event_counts(sim))
    
    #1,79216 125
    #-1,06915 82
    
    #-1,0943 86
    #1,68242 121

    return sim, result


def loss_control_event_counts(sim):
    counts = {}
    for event in sim.loss_control_events:
        action = event["action"]
        counts[action] = counts.get(action, 0) + 1
    return counts


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the OPPW24 research backtest with selected entry loss protections.",
    )
    parser.add_argument(
        "--leverage_override",
        action="store_true",
        help="Use the fixed 1.765 sizing divisor instead of 20 / LEVERAGE.",
    )
    parser.add_argument(
        "--arithmetic-last-two",
        action="store_true",
        help="Skip when the arithmetic sum of the last two weekly outcomes is -2.00% or lower.",
    )
    parser.add_argument(
        "--gap-momentum",
        action="store_true",
        help="Defer/skip when cash gap is >=1.00% and momentum 20 is <=-0.50%.",
    )
    parser.add_argument(
        "--tuesday-normalization",
        action="store_true",
        help="After a gap-momentum defer, require Tuesday within +/-0.50% of Friday.",
    )
    parser.add_argument(
        "--premarket-low",
        action="store_true",
        help="Skip when premarket range is >=0.80% and its close is in the bottom 15%.",
    )
    parser.add_argument(
        "--all-protections",
        "--all-protection",
        action="store_true",
        help="Enable every available entry loss protection.",
    )
    return parser


def loss_protection_options(args):
    all_protections = bool(args.all_protections)
    return {
        "loss_control_lookback": 2 if (all_protections or args.arithmetic_last_two) else None,
        "arithmetic_loss_control_enabled": all_protections or args.arithmetic_last_two,
        "gap_momentum_enabled": all_protections or args.gap_momentum,
        "tuesday_normalization_enabled": all_protections or args.tuesday_normalization,
        "premarket_low_enabled": all_protections or args.premarket_low,
    }


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    options = loss_protection_options(args)
    print("loss protections", {key: value for key, value in options.items() if key != "loss_control_lookback"})
    run_backtest(leverage_override=args.leverage_override, **options)
