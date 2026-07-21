from datetime import datetime, timedelta
import os
import matplotlib.pyplot as plt
import numpy as np
import math
import random
import pickle
from pathlib import Path

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
            if fname[-1] == "txt":
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
                
                granular = int((self.balance/(20/LEVERAGE)/2240))*2240
                    
                #change = round(close_price/open_price-1,4)
                change = int((close_price/open_price-1)*10000)/10000
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
                    print(LEVERAGE, granular, self.balance,self.trade_no, time,trade_type, open_date, close_date, date_diff(open_date, close_date)+1, change, math.pow(self.balance/self.deposited, 1/self.trade_no), ratio, avg_loss, avg_win)
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
                
                if(change < -0.0035):
                    self.classD += 1
                elif(change == -0.0035):
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
            
        thursday_SL = 1-thursday_stop
        friday_SL = 1-friday_stop
        
        for date in sorted(self.quotes):
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
            
            print(date)
            
            openest = quotes[4][0]
            opon = quotes[934][0]
            close = quotes[1324][3]

            tpp = tpps[weekday_index]

            close_price = 0
            close_date = date
            trade_type = ""
            i = 1324

            new_week_entry = (date_diff(prev_date, date) > 1 and weekday_index in (0, 1))

            # --------------------------------------------------------
            # Close previous position at the previous session close.
            # This must happen before yearly accounting and sizing.
            # --------------------------------------------------------

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
                    self.balance -= tax
                    self.gained = 0

            # --------------------------------------------------------
            # Calculate leverage, stop and sizing after the exit.
            # --------------------------------------------------------

            if (self.prev_full_week_change < -0.025 or self.prev_change < -0.007) and self.leverage == 8:
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

            if close_price > 0 and open_price > 0:
                self.sell(i,open_price,close_price,open_date,close_date,trade_type,LEVERAGE,debug)

                open_price = 0
                close_price = 0
                qqq_open_price = 0
                open_date = ""

            # --------------------------------------------------------
            # Open the new weekly position at the cash-session open.
            # --------------------------------------------------------

            if new_week_entry and open_price == 0:
                open_price = opon
                self.prev_open = opon
                open_date = date
                qqq_open_price = qqq_open
                self.trade_no += 1

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
                if qqq_close > qqq_open_price * (1 + tpp):
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
        #print(TP, int(self.deposited),int(self.balance),round(self.lost/self.balance,3),self.dd)
        #print(start_date, end_date, self.classA, self.classB, self.classC, self.classD, self.cumulative_change, end=" ")
        #print(self.balance, self.max_equity, round(self.balance/self.max_equity, 4), self.deposited)

        #print_wallet(end_date, round(WIN/(WIN+LOSS), 2), 100*(1-MAX_DD),debug,MAX_EQUITY,WIN_AMOUNT/LOSS_AMOUNT,TIMEOUT,SL)
        if(plots == True):
            plotting(self.equity_history, self.deposit_history)        
        
        #return build_backtest_result(initial_balance=initial_balance, final_balance=self.balance, deposited=self.deposited, 
        #    trade_returns=self.trade_returns, days_in_position=self.days_in_position, start_date=start_date, end_date=end_date)
        
        total_cagr = round(self.balance/self.deposited, 2)
        years = (self.trade_no*7)/365
        cagr = round(pow(total_cagr, 1/years), 2)
        
        return [int(self.balance), int(self.deposited), total_cagr, cagr,self.days_in_position,round(1-self.max_dd,3),self.max_dd_duration,self.dd_total_duration]
        
def bench_weeks(weeks, sim, LEVERAGE, SL, BE):
    start_date = ""
    end_date = "20260706"
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
                    if(date not in sim.quotes and date != "20010914"):
                        break
        if(end_date not in sim.quotes):
            end_date = add_days(end_date, -1)
            if(end_date not in sim.quotes):
                end_date = add_days(end_date, -1)
                if(end_date not in sim.quotes):
                    end_date = add_days(end_date, -1)
                    if(end_date not in sim.quotes):
                        continue
        
        result = sim_i.process(sim_i.quotes, "QQQ", date, end_date, LEVERAGE, 0.1, SL, BE, False,False)
                        
if __name__ == "__main__":
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
    
    #bench_weeks(500, sim, LEVERAGE, SL, BE)
    
    sim_i = Sim()
    
    tpps = [0.007,0.02,0.05,0.05,0.05]
    print(tpps)
    result = sim.process(sim_i.quotes, "QQQ","20180413", "20260717", LEVERAGE, tpps, SL, BE, 0.004,0.004, 30000, False,False,True,True)
    print(result)
    
    #1,79216 125
    #-1,06915 82
    
    #-1,0943 86
    #1,68242 121