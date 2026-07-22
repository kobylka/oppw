from datetime import datetime, timedelta
import os
import matplotlib.pyplot as plt
import numpy as np
import math
import random

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
            
        self.lost = 0
        self.dd = 0
            
        self.equity_history = []
        self.deposit_history = []
        
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
                    date = datetime.strptime(dukascopy_date, "%d.%m.%Y").strftime("%Y%m%d")
                    
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

    def sell(self, open_price, close_price, open_date, close_date, trade_type, debug=False):
                change = round(close_price/open_price-1,4)
                #print(change)
                self.cumulative_change *= change*LEVERAGE+1
                lev = LEVERAGE
                if(self.prev_change < -0.02):
                    lev = 6
                #if(max_equity > 0):
                #    if(balance/max_equity > 0.6):
                #        lev = 6
                self.gained += self.balance*change*lev
                self.balance += self.balance*change*lev
                if(debug == True):
                    print(self.trade_no, trade_type, open_date, close_date, date_diff(open_date, close_date)+1, change, math.pow(self.balance/self.deposited, 1/self.trade_no))
                if(change*lev < -0.1): self.lost += self.balance*change*lev
                if(self.balance > self.max_equity):
                    if(self.n > 2):
                        self.dd += self.n
                        #if(debug is True): print(date,n,round(100*(local_dd_equity/max_equity-1),3))
                        #print(date,n,round(100*(local_dd_equity/max_equity-1),3))
                    self.max_equity = self.balance
                    self.local_dd_equity = 1000000000000
                    self.n = 0
                else:
                    if(self.balance < self.local_dd_equity):
                        self.local_dd_equity = self.balance
                    self.n+=1
                
                self.prev_change = change
                self.break_even = False
                
                if(change < -0.0035):
                    self.classD += 1
                elif(change == -0.0035):
                    self.classC += 1
                elif(change < 0.017):
                    self.classB += 1
                else:
                    self.classA += 1
                    
                self.equity_history.append(self.balance)
                self.deposit_history.append(self.deposited)
    def process4(self,quotes, stock, start_date, end_date, LEVERAGE, TP, SL, BE, debug, plots):
        prev_date = "20000101"
        prev_year = start_date
        
        
        self.classA = 0
        self.classB = 0
        self.classC = 0
        self.classD = 0  
        
        suma_total = 0
            
        initial   = 80000
        self.deposited = initial
        self.balance   = initial
        trade_type = ""
        
        date = ""
        
        open_price = 0
        
        yearlies = []
        prev_year = start_date
        
        prev_equity = initial
        prev_depo = start_date
            
        for date in self.quotes:
            if(date < start_date): continue
            if(date == end_date): break
            date_obj = datetime.strptime(date, "%Y%m%d").date()

            # Check if it's Monday
            is_monday = date_obj.weekday() == 0
            is_tuesday = date_obj.weekday() == 1
            is_wednesday = date_obj.weekday() == 2
            is_thursday = date_obj.weekday() == 3
            is_friday = date_obj.weekday() == 4
            is_saturday = date_obj.weekday() == 5
            is_sunday = date_obj.weekday() == 6
            
            if(is_saturday or is_sunday): continue
            
            
            if(prev_year[:4] != date[:4] and self.balance > 0 and open_price == 0):
                yearlies.append(round(100*(self.balance/prev_equity-1),1))
                prev_year = date
                prev_equity = self.balance
                tax = self.gained*0.00
                
                #print(date, self.balance, self.gained, tax, self.balance-tax)
                if(tax > 0):
                    self.balance -= tax
                    self.gained = 0
                    
            if(date_diff(prev_depo,date) > 30):
                self.balance += 3000
                self.deposited += 3000
                prev_depo = date
            
            close_price = 0
            close_date = date
            
            step = 0.15
            
            quant = 6000
            max_pos_count = 5
            
            init = int(self.balance/120000)*quant
            if(suma_total < 5000000):
                init = int(self.balance/60000)*quant
            if(self.balance < 60000):
                init = 1850*math.floor(self.balance/(max_pos_count*1850))
            if(debug is True):
                print(init, int(self.balance), math.floor(self.balance/(max_pos_count*1850)))
            #init = 0
            if(init == 0): init = 10000
            base_value = init
            k = 0
            
            open_price = 0
            pos_count = 0
            avg_buy = 0
            
            buy_prices = []
            
            #930 - 15:29
            #870 - 14:29
            
            candle_start = 930
            candle_end = 1320
            
            print(date)
            
            day_open = self.quotes[date][stock][candle_start][0]
            day_close = self.quotes[date][stock][candle_end][3]
            day_high = self.quotes[date][stock][candle_start][1]
            
            stop_loss = 0 
            
            for i in range(candle_start, candle_end+1):
                opon = self.quotes[date][stock][i][0]
                high = self.quotes[date][stock][i][1]
                low  = self.quotes[date][stock][i][2]
                close = self.quotes[date][stock][i][3]
                
                if(high > day_high): day_high = high
                
                if(open_price == 0):
                    k+=base_value
                    local_open = opon
                    open_price = opon
                    pos_count = 1
                    print(pos_count, local_open)
                    avg_buy = opon
                    buy_prices.append(opon)
                
                last_price = buy_prices[len(buy_prices)-1]
                ups = int(100*(high/last_price-1)/step)
                #print(date, pos_count, pos_count+ups+1)
                for j in range(0,ups):
                    if(pos_count < max_pos_count):
                        k+=base_value
                        local_open = round(open_price*(1+step/100)**pos_count, 2)
                        avg_buy = (avg_buy*pos_count + local_open)/(pos_count+1)
                        pos_count += 1
                        buy_prices.append(local_open)
                        print(pos_count, local_open)
                
                if(pos_count > 5 and low < avg_buy):
                    stop_loss = avg_buy
                    break
                elif(low/avg_buy < 0.995):
                    stop_loss = avg_buy*0.995
                    print(date, i)
                    break
            
                
            suma_change = 0
            suma_value = 0
            close_price = day_close
            if(stop_loss > 0):
                close_price = stop_loss
            for local_open in buy_prices:
                local_change = (close_price/local_open-1)*20
                #print(local_change, local_open, close_price)
                suma_change += local_change
                suma_value += base_value*local_change
            
            print(date, int(avg_buy), int(day_high), int(close_price), k, close_price/avg_buy, suma_change, round(suma_value, 2))
                    
            self.balance += suma_value
            
            self.gained += suma_value
            
            suma_total += suma_value
            self.equity_history.append(suma_total)
            self.deposit_history.append(k)
            
            #print(opon, close, avg_buy, avg_sell, high)
            
            if(debug is True):
                print(date, ups, downs, int(suma_value), k, round(100*(suma_value/k), 3), suma_total)
            #print(opon, high, low,close, low/close)
            
        #print(self.deposited)       
        #print(yearlies)
        #print(TP, int(self.deposited),int(self.balance),round(self.lost/self.balance,3),self.dd)
        print(start_date, end_date, int(self.balance), self.deposited)
        #print_wallet(end_date, round(WIN/(WIN+LOSS), 2), 100*(1-MAX_DD),debug,MAX_EQUITY,WIN_AMOUNT/LOSS_AMOUNT,TIMEOUT,SL)
        if(plots == True):
            plotting(self.equity_history, self.deposit_history)
        
        ret_balance = self.balance
        
        return [0, date, ret_balance]
        
    def process5(self,quotes, stock, start_date, end_date, LEVERAGE, TP, SL, BE, debug, plots):
        prev_date = "20000101"
        prev_year = start_date
        
        suma_total = 0
            
        initial   = 80000
        self.deposited = initial
        self.balance   = initial
        trade_type = ""
        
        date = ""
        
        open_price = 0
        
        yearlies = []
        prev_year = start_date
        
        prev_equity = initial
        prev_depo = start_date
            
        for date in self.quotes:
            if(date < start_date): continue
            if(date == end_date): break
            date_obj = datetime.strptime(date, "%Y%m%d").date()

            # Check if it's Monday
            is_monday = date_obj.weekday() == 0
            is_tuesday = date_obj.weekday() == 1
            is_wednesday = date_obj.weekday() == 2
            is_thursday = date_obj.weekday() == 3
            is_friday = date_obj.weekday() == 4
            is_saturday = date_obj.weekday() == 5
            is_sunday = date_obj.weekday() == 6
            
            if(is_saturday or is_sunday): continue
            
            
            if(prev_year[:4] != date[:4] and self.balance > 0 and open_price == 0):
                yearlies.append(round(100*(self.balance/prev_equity-1),1))
                prev_year = date
                prev_equity = self.balance
                tax = self.gained*0.00
                
                #print(date, self.balance, self.gained, tax, self.balance-tax)
                if(tax > 0):
                    self.balance -= tax
                    self.gained = 0
                    
            if(date_diff(prev_depo,date) > 30):
                self.balance += 3000
                self.deposited += 3000
                prev_depo = date
            
            close_price = 0
            close_date = date
           
           
            step = 0.2
            
            quant = 7500
            max_pos_count = 4
            
            init = int(self.balance/60000)*quant
            if(self.balance > 100000000):
                init = int(self.balance/180000)*quant
            elif(self.balance > 50000000):
                init = int(self.balance/120000)*quant
            if(debug is True):
                print(init, int(self.balance), math.floor(self.balance/(max_pos_count*1850)))
            #init = 0
            if(init == 0): init = 1850*math.floor(self.balance/(max_pos_count*1850))
            base_value = init
            k = 0
            
            L_pos_count = 0
            S_pos_count = 0
            avg_buy = 0
            avg_sell = 0
            
            buy_prices = []
            sell_prices = []
            
            #930 - 15:29
            #870 - 14:29
            
            candle_start = 930
            candle_end = 1320
            
            midnight_open = self.quotes[date][stock][0][0]
            
            day_open = self.quotes[date][stock][candle_start][0]
            day_close = self.quotes[date][stock][candle_end][3]
            day_high = self.quotes[date][stock][candle_start][1]
            day_low = 1000000
            
            daily_max_gain = 0
            
            sl_gain = 0
            sl_price = 0
            
            for i in range(candle_start, candle_end+1):
                opon = self.quotes[date][stock][i][0]
                high = self.quotes[date][stock][i][1]
                low  = self.quotes[date][stock][i][2]
                close = self.quotes[date][stock][i][3]
                
                if(high > day_high): day_high = high
                if(low < day_low): day_low = low
                
                if(len(buy_prices) > 0):
                    last_price = buy_prices[len(buy_prices)-1]
                else:
                    last_price = day_open
                ups = int(100*(high/last_price-1)/step)
                #print(date, L_pos_count, L_pos_count+ups+1)
                for j in range(0,ups):
                    if(L_pos_count < max_pos_count):
                        k+=base_value
                        local_open = round(day_open*(1+step/100)**(L_pos_count+1), 2)
                        avg_buy = (avg_buy*L_pos_count + local_open)/(L_pos_count+1)
                        L_pos_count += 1
                        buy_prices.append(local_open)
                        #print("L", L_pos_count, local_open)
                
                if(len(sell_prices) > 0):
                    last_price = sell_prices[len(sell_prices)-1]
                else:
                    last_price = day_open
                downs = -int(100*(low/last_price-1)/step)
                #if(downs > 0):
                    #print(date, low, last_price, S_pos_count, downs)
                for j in range(0,downs):
                    if(S_pos_count < max_pos_count):
                        k+=base_value
                        local_open = round(day_open*(1-step/100)**(S_pos_count+1), 2)
                        avg_sell = (avg_sell*S_pos_count + local_open)/(S_pos_count+1)
                        S_pos_count += 1
                        sell_prices.append(local_open)
                        #print("S", S_pos_count, local_open)
                
                minute_gain = 0
                for local_open in buy_prices:
                    local_change = (close/local_open-1)*20
                    minute_gain += base_value*local_change
                
                for local_open in sell_prices:
                    local_change = (1-close/local_open)*20
                    minute_gain += base_value*local_change
                
                if(minute_gain > daily_max_gain):
                    daily_max_gain = minute_gain
                elif(daily_max_gain > 0 and daily_max_gain/self.balance > 0.1):
                    sl_price = close
                    print(i, "SL", int(minute_gain), int(daily_max_gain))
                    break
                elif(minute_gain/self.balance < -0.02):
                    sl_price = close
                    print(i, "LS", int(minute_gain), int(daily_max_gain))
                    break
                
            suma_change = 0
            suma_value = 0
            close_price = day_close
            if(sl_price > 0):
                close_price = sl_price
                
            for local_open in buy_prices:
                local_change = (close_price/local_open-1)*20
                #print("L", local_change, local_open, close_price, base_value*local_change)
                suma_change += local_change
                suma_value += base_value*local_change
            
            for local_open in sell_prices:
                local_change = (1-close_price/local_open)*20
                #print("S", local_change, local_open, close_price, base_value*local_change)
                suma_change += local_change
                suma_value += base_value*local_change
            
            #print("AVGL:", int(avg_buy), "H:", int(day_high), "L:", int(day_low), "C:", int(close_price))
            print(date, k, int(suma_value), int(daily_max_gain), int(self.balance))
            #print()
                    
            self.balance += suma_value
            self.gained += suma_value
            
            suma_total += suma_value
            self.equity_history.append(suma_total)
            #self.deposit_history.append(k)
            
            #print(opon, close, avg_buy, avg_sell, high)
            
            if(debug is True):
                print(date, ups, downs, int(suma_value), k, round(100*(suma_value/k), 3), suma_total)
            #print(opon, high, low,close, low/close)
            
        #print(self.deposited)       
        #print(yearlies)
        #print(TP, int(self.deposited),int(self.balance),round(self.lost/self.balance,3),self.dd)
        print(start_date, end_date, int(self.balance), self.deposited)
        #print_wallet(end_date, round(WIN/(WIN+LOSS), 2), 100*(1-MAX_DD),debug,MAX_EQUITY,WIN_AMOUNT/LOSS_AMOUNT,TIMEOUT,SL)
        if(plots == True):
            plotting(self.equity_history, self.deposit_history)
        
        ret_balance = self.balance
        
        return [0, date, ret_balance]
        
    def process6(self,quotes, stock, start_date, end_date, LEVERAGE, TP, SL, BE, debug, plots):
        prev_date = "20000101"
        prev_year = start_date
        
        suma_total = 0
            
        initial   = 80000
        self.deposited = initial
        self.balance   = initial
        trade_type = ""
        
        date = ""
        
        open_price = 0
        
        yearlies = []
        prev_year = start_date
        
        prev_equity = initial
        prev_depo = start_date
            
        for date in self.quotes:
            if(date < start_date): continue
            if(date == end_date): break
            date_obj = datetime.strptime(date, "%Y%m%d").date()

            # Check if it's Monday
            is_monday = date_obj.weekday() == 0
            is_tuesday = date_obj.weekday() == 1
            is_wednesday = date_obj.weekday() == 2
            is_thursday = date_obj.weekday() == 3
            is_friday = date_obj.weekday() == 4
            is_saturday = date_obj.weekday() == 5
            is_sunday = date_obj.weekday() == 6
            
            if(is_saturday or is_sunday): continue
            
            
            if(prev_year[:4] != date[:4] and self.balance > 0 and open_price == 0):
                yearlies.append(round(100*(self.balance/prev_equity-1),1))
                prev_year = date
                prev_equity = self.balance
                tax = self.gained*0.00
                
                #print(date, self.balance, self.gained, tax, self.balance-tax)
                if(tax > 0):
                    self.balance -= tax
                    self.gained = 0
                    
            if(date_diff(prev_depo,date) > 30):
                self.balance += 3000
                self.deposited += 3000
                prev_depo = date
            
            close_price = 0
            close_date = date
           
           
            step = 0.15
            
            quant = 6000
            max_pos_count = 5
            
            init = int(self.balance/60000)*quant
            if(self.balance > 100000000):
                init = int(self.balance/180000)*quant
            elif(self.balance > 50000000):
                init = int(self.balance/120000)*quant
            if(debug is True):
                print(init, int(self.balance), math.floor(self.balance/(max_pos_count*1850)))
            #init = 0
            if(init == 0): init = 1850*math.floor(self.balance/(max_pos_count*1850))
            base_value = init
            k = 0
            
            L_pos_count = 0
            S_pos_count = 0
            avg_buy = 0
            avg_sell = 0
            
            buy_prices = []
            sell_prices = []
            
            #930 - 15:29
            #870 - 14:29
            
            candle_start = 930
            candle_end = 1320
            
            midnight_open = self.quotes[date][stock][0][0]
            
            day_open = self.quotes[date][stock][candle_start][0]
            day_close = self.quotes[date][stock][candle_end][3]
            day_high = self.quotes[date][stock][candle_start][1]
            day_low = 1000000
            
            daily_max_gain = 0
            
            sl_gain = 0
            sl_price = 0
            j = 0
            
            minutes = 5
            
            for i in range(candle_start, candle_end+1):
                opon = self.quotes[date][stock][i][0]
                high = self.quotes[date][stock][i][1]
                low  = self.quotes[date][stock][i][2]
                close = self.quotes[date][stock][i][3]
                
                prev_opon = self.quotes[date][stock][i-minutes][0]
                prev_high = self.quotes[date][stock][i-minutes][1]
                prev_low  = self.quotes[date][stock][i-minutes][2]
                prev_close = self.quotes[date][stock][i-minutes][3]
                
                if(high > day_high): day_high = high
                if(low < day_low): day_low = low
                
                if(low/prev_high < 0.995 and len(buy_prices) == 0 and len(sell_prices) == 0):
                    print(date, i)
                    sell_prices.append(close)
                    k = self.balance
                    j = i
                minute_gain = 0
                for local_open in buy_prices:
                    local_change = (close/local_open-1)*20
                    minute_gain += k*local_change
                
                for local_open in sell_prices:
                    local_change = (1-close/local_open)*20
                    minute_gain += k*local_change
                    print(i, minute_gain)
                
                if(i-j == 10):
                    sl_price = close
                    print(i, "SL", int(minute_gain), int(daily_max_gain))
                    break
                elif(minute_gain/self.balance < -0.05):
                    sl_price = close
                    print(i, "LS", int(minute_gain), int(daily_max_gain))
                    break
                elif(i == candle_end):
                    sl_price = close
                    print(i, "TO", int(minute_gain), int(daily_max_gain))
                    break
                
            suma_change = 0
            suma_value = 0
            close_price = day_close
            if(sl_price > 0):
                close_price = sl_price
                
            for local_open in buy_prices:
                local_change = (close_price/local_open-1)*20
                #print("L", local_change, local_open, close_price, base_value*local_change)
                suma_change += local_change
                suma_value += k*local_change
            
            for local_open in sell_prices:
                local_change = (1-close_price/local_open)*20
                #print("S", local_change, local_open, close_price, base_value*local_change)
                suma_change += local_change
                suma_value += k*local_change
            
            #print("AVGL:", int(avg_buy), "H:", int(day_high), "L:", int(day_low), "C:", int(close_price))
            print(date, k, int(suma_value), int(daily_max_gain), int(self.balance))
            #print()
                    
            self.balance += suma_value
            self.gained += suma_value
            
            suma_total += suma_value
            self.equity_history.append(self.balance)
            #self.deposit_history.append(k)
            
            #print(opon, close, avg_buy, avg_sell, high)
            
            if(debug is True):
                print(date, ups, downs, int(suma_value), k, round(100*(suma_value/k), 3), suma_total)
            #print(opon, high, low,close, low/close)
            
        #print(self.deposited)       
        #print(yearlies)
        #print(TP, int(self.deposited),int(self.balance),round(self.lost/self.balance,3),self.dd)
        print(start_date, end_date, int(self.balance), self.deposited)
        #print_wallet(end_date, round(WIN/(WIN+LOSS), 2), 100*(1-MAX_DD),debug,MAX_EQUITY,WIN_AMOUNT/LOSS_AMOUNT,TIMEOUT,SL)
        if(plots == True):
            plotting(self.equity_history, self.deposit_history)
        
        ret_balance = self.balance
        
        return [0, date, ret_balance]
        
    def process3(self,quotes, stock, start_date, end_date, LEVERAGE, TP, SL, BE, debug, plots):
        prev_date = "20000101"
        prev_year = start_date
        
        
        self.classA = 0
        self.classB = 0
        self.classC = 0
        self.classD = 0  
        
        suma_total = 0
            
        initial   = 80000
        self.deposited = initial
        self.balance   = initial
        trade_type = ""
        
        date = ""
        
        open_price = 0
        
        yearlies = []
        prev_year = start_date
        
        prev_equity = initial
        prev_depo = start_date
        
        for date in self.quotes:
            if(date < start_date): continue
            if(date == end_date): break
            date_obj = datetime.strptime(date, "%Y%m%d").date()
            
            
            if(prev_year[:4] != date[:4] and self.balance > 0 and open_price == 0):
                yearlies.append(round(100*(self.balance/prev_equity-1),1))
                prev_year = date
                prev_equity = self.balance
                tax = self.gained*0.00
                
                #print(date, self.balance, self.gained, tax, self.balance-tax)
                if(tax > 0):
                    self.balance -= tax
                    self.gained = 0
                    
            if(date_diff(prev_depo,date) > 30000):
                self.balance += 3000
                self.deposited += 3000
                prev_depo = date

            # Check if it's Monday
            is_monday = date_obj.weekday() == 0
            is_tuesday = date_obj.weekday() == 1
            is_wednesday = date_obj.weekday() == 2
            is_thursday = date_obj.weekday() == 3
            is_friday = date_obj.weekday() == 4
            is_saturday = date_obj.weekday() == 5
            is_sunday = date_obj.weekday() == 6
            
            opon = self.quotes[date][stock][0]
            high = self.quotes[date][stock][1]
            low  = self.quotes[date][stock][2]
            close = self.quotes[date][stock][3]
            
            
            buy_prices = []
            sell_prices = []
            
            close_price = 0
            close_date = date
            
            step = 0.3
            init = int(self.balance/240000)*10000
            if(suma_total < 100000):
                init = int(self.balance/60000)*10000
            elif(suma_total < 5000000):
                init = int(self.balance/120000)*10000
            elif(suma_total < 10000000):
                init = int(self.balance/180000)*10000
            if(self.balance < 60000):
                init = 1850*math.floor(self.balance/11100)
            if(debug is True):
                print(init, int(self.balance), math.floor(self.balance/11100))
            #init = 0
            if(init == 0): init = 10000
            base_value = init
            k = 0
            
            ups = abs(int(100*(high/opon-1)/step))
            downs = 0
            
            if(ups > 6): ups = 6
            if(downs > 6): downs = 6
            
            suma_change = 0
            suma_value = 0
            
            k+=base_value
            local_open = opon
            local_change = (close/local_open-1)*20
            suma_change += local_change
            suma_value += base_value*local_change
            #print(0,ups, opon, opon, close, local_change, suma_change, suma_value)
            avg_buy = opon
            buy_prices.append(opon)
            i = 0
            for i in range(1,ups):
                k+=base_value
                local_open = round(opon*(1+step/100)**i, 2)
                local_change = (close/local_open-1)*20
                suma_change += local_change
                suma_value += base_value*local_change
                avg_buy = (avg_buy*i + local_open)/(i+1)
                buy_prices.append(local_open)
                #print(i, opon, local_open, close, local_change, suma_change, suma_value)
            
            SL_price = 0
            if(ups > 2 and close < opon):
                SL_price = opon
                #print(low/opon, SL_price, avg_buy, 20*(SL_price/avg_buy-1))
                suma_value = 20*(SL_price/avg_buy-1)*k
            elif(low/opon < 0.985):
                SL_price = opon*0.985
                #print(low/opon, SL_price, avg_buy, 20*(SL_price/avg_buy-1))
                suma_value = 20*(SL_price/avg_buy-1)*k
            if(debug is True):
                print(avg_buy, SL_price, SL_price/avg_buy)
            
            #if(i>j and high/close > 1.01):
                #print(j*base_value, (avg_sell/high-1))
                #print(avg_sell, avg_buy, i+1, j+1)
                #SL = 0
                #SL_threshold = 0.01
                #for a in range(int(avg_buy*100), int(high*100)):
                    #a=a/100
                    #sum_gain = 0
                    #for b in buy_prices:
                    #    sum_gain += ((a/b-1)*20)
                    #sum_loss = 0
                    #for b in sell_prices:
                    #    sum_loss += ((b/a-1)*20)
                    #pnl = sum_loss*base_value+sum_gain*base_value
                    #print(a, pnl)
                    #if(pnl/k > SL_threshold):
                        #print(a,pnl)
                        #break
            #elif(i<j and low/opon < 0.985):
                #SL = 0
                #SL_threshold = 0.01
                #for a in range(int(opon * 100), int(low * 100) - 1, -1):
                    #a=a/100
                    #sum_gain = 0
                    #for b in buy_prices:
                    #    sum_gain += ((a/b-1)*20)
                    #sum_loss = 0
                    #for b in sell_prices:
                    #    sum_loss += ((b/a-1)*20)
                    #pnl = sum_loss*base_value+sum_gain*base_value
                    #print(low,a, pnl)
                    #if(pnl/k > SL_threshold):
                        #print(a,pnl)
                        #break
            
                #if(pnl > 0):
                    #suma_value = pnl
            
            self.balance += suma_value
            
            self.gained += suma_value
            
            suma_total += suma_value
            self.equity_history.append(suma_total)
            self.deposit_history.append(k)
            
            #print(opon, close, avg_buy, avg_sell, high)
            
            if(debug is True):
                print(date, ups, downs, int(suma_value), k, round(100*(suma_value/k), 3), suma_total)
            #print(opon, high, low,close, low/close)
            
        #print(self.deposited)       
        #print(yearlies)
        #print(TP, int(self.deposited),int(self.balance),round(self.lost/self.balance,3),self.dd)
        print(start_date, end_date, int(self.balance), self.deposited)
        #print_wallet(end_date, round(WIN/(WIN+LOSS), 2), 100*(1-MAX_DD),debug,MAX_EQUITY,WIN_AMOUNT/LOSS_AMOUNT,TIMEOUT,SL)
        if(plots == True):
            plotting(self.equity_history, self.deposit_history)
        
        ret_balance = self.balance
        
        return [0, date, ret_balance]
        
def bench_weeks(weeks, sim, LEVERAGE, SL, BE):
    start_date = ""
    for date in sim.quotes:
        start_date = date
        break
      
    for i in range(0,2000):
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
                    if(date not in sim.quotes):
                        break
        if(end_date not in sim.quotes):
            end_date = add_days(end_date, -1)
            if(end_date not in sim.quotes):
                end_date = add_days(end_date, -1)
                if(end_date not in sim.quotes):
                    end_date = add_days(end_date, -1)
                    if(end_date not in sim.quotes):
                        continue
        
        result = sim_i.process3(sim_i.quotes, "QQQ", date, end_date, LEVERAGE, 0.1, SL, BE, False,False)
                        
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
    
    sim = Sim()
    
    #sim.read_quotes(files, "20220103")
    sim.read_csv_quotes(files, "20220103")
    
    LEVERAGE = 6
    SL = (100-50/LEVERAGE)/100
    BE = 0.9965
    
    #bench_weeks(52, sim, LEVERAGE, SL, BE)
    
    sim_i = Sim()
    #result = sim.process3(sim_i.quotes, "QQQ", "20220103", "20220228", LEVERAGE, 0.1, SL, BE, False,True)
    #result = sim.process4(sim_i.quotes, "QQQ", "20220103", "20250408", LEVERAGE, 0.1, SL, BE, False,True)
    result = sim.process5(sim_i.quotes, "QQQ1", "20220102", "20250104", LEVERAGE, 0.1, SL, BE, False,True)