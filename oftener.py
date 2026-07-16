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
    
    def process(self,quotes, stock, start_date, end_date, LEVERAGE, TP, SL, BE, debug, plots):
        global balance,deposited
        
        prev_date = "20000101"
        prev_year = start_date
        
        equity_history = []
        deposit_history = []
        
        yearlies = []
            
        initial   = 20000
        deposited = initial
        balance   = initial
        
        lost = 0
        dd = 0
        max_equity = 0
        local_dd_equity = 1000000000000
        
        open_price = 0
        break_even = False
        
        i=0
        n=0
        
        change = 0
        for date in quotes:
            if(date == end_date): break
            date_obj = datetime.strptime(date, "%Y%m%d").date()
            
            
            #if(change < 0 and balance < 1000000):
            #    balance += 1000
             #   deposited += 1000

            # Check if it's Monday
            is_monday = date_obj.weekday() == 0
            is_tuesday = date_obj.weekday() == 1
            
            opon = quotes[date][stock][0]
            high = quotes[date][stock][1]
            low  = quotes[date][stock][2]
            close = quotes[date][stock][3]
            
            close_price = 0
            close_date = date
                
            if(date_diff(prev_date, date) > 2 and open_price > 0):
                close_date = prev_date
                close_price = quotes[prev_date][stock][3]
                trade_type = "TO"
            elif(open_price > 0):
                if(open_price*SL > opon):
                    close_price = opon
                    trade_type = "FUCK"
                elif(break_even == True):
                    if(opon > open_price*BE):
                        close_price = opon
                        trade_type = "BO"
                    elif(high > open_price*BE):
                        close_price = open_price*BE
                        trade_type = "BH"
                        
                
                if(close < open_price*BE):
                    break_even = True
            
            if(close_price > 0 and open_price > 0):
                change = round(close_price/open_price-1,4)
                balance += balance*change*LEVERAGE
                if(debug == True):
                    print(i, trade_type, open_date, close_date, date_diff(open_date, close_date)+1, change, math.pow(balance/deposited, 1/i))
                if(change*LEVERAGE < -0.1): lost += balance*change*LEVERAGE
                if(balance > max_equity):
                    if(n > 2):
                        dd += n
                        if(debug is True): print(date,n,round(100*(local_dd_equity/max_equity-1),3))
                    max_equity = balance
                    local_dd_equity = 1000000000000
                    n = 0
                else:
                    if(balance < local_dd_equity):
                        local_dd_equity = balance
                    n+=1
                
                change = 0
                open_price = 0
                close_price = 0
                open_date = ""
                break_even = False
                    
                equity_history.append(balance)
                deposit_history.append(deposited)
                
            if(date_diff(prev_date, date) > 1 and (is_monday is True or is_tuesday is True)):
                if(balance < 1000000):
                    balance += 750
                    deposited += 750
                open_price = opon
                open_date  = date
                i+=1
            if(low < open_price*SL):
                close_date = date
                close_price = open_price*SL
                trade_type = "SL"
            elif(opon > open_price*(1+TP) and open_price > 0):
                close_date = date
                close_price = opon
                trade_type = "OH"
            elif(close > open_price*(1+TP) and open_price > 0):
                close_date = date
                close_price = close
                trade_type = "CH"
            
            if(close_price > 0 and open_price > 0):
                change = round(close_price/open_price-1,4)
                balance += balance*change*LEVERAGE
                if(debug == True):
                    print(i, trade_type, open_date, close_date, date_diff(open_date, close_date)+1, change, math.pow(balance/deposited, 1/i))
                if(change*LEVERAGE < -0.1): lost += balance*change*LEVERAGE
                
                if(balance > max_equity):
                    if(n > 2):
                        dd += n
                        if(debug is True): print(date,n,round(100*(local_dd_equity/max_equity-1),3))
                    max_equity = balance
                    local_dd_equity = 1000000000000
                    n = 0
                else:
                    if(balance < local_dd_equity):
                        local_dd_equity = balance
                    n+=1
                
                change = 0
                open_price = 0
                close_price = 0
                open_date = ""
                break_even = False
                    
                equity_history.append(balance)
                deposit_history.append(deposited)
                
            prev_date = date
            
            if(balance < 10000):
                deposited += 10000-balance
                balance += 10000-balance
               
        
        #print(yearlies)
        print(TP, int(deposited),int(balance),round(lost/balance,3),dd)
        #print_wallet(end_date, round(WIN/(WIN+LOSS), 2), 100*(1-MAX_DD),debug,MAX_EQUITY,WIN_AMOUNT/LOSS_AMOUNT,TIMEOUT,SL)
        if(plots == True):
            plotting(equity_history, deposit_history)
        
        ret_balance = balance
        
        return [0, date, ret_balance]
        
    def process2(self,quotes, stock, start_date, end_date, LEVERAGE, TP, SL, BE, debug, plots):
        prev_date = "20000101"
        prev_year = start_date
        
        
        self.classA = 0
        self.classB = 0
        self.classC = 0
        self.classD = 0  
            
        initial   = 170000
        self.deposited = initial
        self.balance   = initial
        trade_type = ""
        
        date = ""
        
        open_price = 0
        
        yearlies = []
        prev_year = start_date
        
        prev_equity = initial
        
        for date in self.quotes:
            if(date < start_date): continue
            if(date == end_date): break
            date_obj = datetime.strptime(date, "%Y%m%d").date()
            
            if(prev_year[:4] != date[:4] and self.balance > 0 and open_price == 0):
                yearlies.append(round(100*(self.balance/prev_equity-1),1))
                prev_year = date
                prev_equity = self.balance
                tax = self.gained*0.00
                
                #print(date, balance, gained, tax, balance-tax)
                if(tax > 0):
                    self.balance -= tax
                    self.gained = 0

            # Check if it's Monday
            is_monday = date_obj.weekday() == 0
            is_tuesday = date_obj.weekday() == 1
            is_wednesday = date_obj.weekday() == 2
            is_thursday = date_obj.weekday() == 3
            is_friday = date_obj.weekday() == 4
            
            opon = self.quotes[date][stock][0]
            high = self.quotes[date][stock][1]
            low  = self.quotes[date][stock][2]
            close = self.quotes[date][stock][3]
            
            close_price = 0
            close_date = date
            
            
            if(open_price > 0):
                if(open_price*SL > opon):
                    close_price = opon
                    trade_type = "FUCK"
                elif(self.break_even == True):
                    if(opon > open_price*BE):
                        close_price = opon
                        trade_type = "BO"   
                    elif(high > open_price*BE):
                        close_price = open_price*BE
                        trade_type = "BH"
                
            if(close < open_price*BE):
                self.break_even = True
            
            if(close_price > 0 and open_price > 0):
                self.sell(open_price, close_price, open_date, close_date, trade_type, debug)
                open_price = 0
                close_price = 0
                open_date = ""
            
            if(is_monday): tpp = 0.017
            if(is_tuesday): tpp = 0.017
            if(is_wednesday): tpp = 0.02
            if(is_thursday): tpp = 0.023
            if(is_friday): tpp = 0.027
            
            if(is_monday): tpp2 = 0.017
            if(is_tuesday): tpp2 = 0.02
            if(is_wednesday): tpp2 = 0.023
            if(is_thursday): tpp2 = 0.027
            if(is_friday): tpp2 = 0.03
            
            if(date_diff(prev_date, date) > 1 and (is_monday is True or is_tuesday is True)):
                if(open_price > 0):
                    close_price = self.quotes[prev_date][stock][3]
                    trade_type = "TO"
                    self.sell(open_price, close_price, open_date, close_date, trade_type, debug)
                    open_price = 0
                    close_price = 0
                    open_date = ""
                if(self.balance < 2000000):
                    self.balance += 750
                    self.deposited += 750
                
                open_price = opon
                open_date  = date
                self.trade_no+=1
            if(low < open_price*SL):
                close_date = date
                close_price = open_price*SL
                trade_type = "SL"
            elif(opon > open_price*(1+tpp2) and open_price > 0):
                close_date = date
                close_price = opon
                trade_type = "OH"
            elif(close > open_price*(1+tpp2) and open_price > 0):
                close_date = date
                close_price = close
                trade_type = "CH"
            elif(is_friday and close_price == 0):
                close_date = date
                close_price = close
                trade_type = "TO"
            
            if(close_price > 0 and open_price > 0):
                self.sell(open_price, close_price, open_date, close_date, trade_type, debug)
                open_price = 0
                close_price = 0
                open_date = ""
                
            prev_date = date
            
            if(self.balance < 10000):
                self.deposited += 10000-self.balance
                self.balance += 10000-self.balance
               
        #print(yearlies)
        #print(TP, int(self.deposited),int(self.balance),round(self.lost/self.balance,3),self.dd)
        print(start_date, end_date, self.classA, self.classB, self.classC, self.classD, self.cumulative_change)
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
        
        result = sim_i.process2(sim_i.quotes, "QQQ", date, end_date, LEVERAGE, 0.1, SL, BE, False,False)
                        
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
    
    sim.read_quotes(files, "20100104")
    
    LEVERAGE = 4
    SL = (100-50/LEVERAGE)/100
    BE = 0.9965
    
    bench_weeks(52, sim, LEVERAGE, SL, BE)
    
    sim_i = Sim()
    result = sim.process2(sim_i.quotes, "QQQ", "20220102", "20251229", LEVERAGE, 0.1, SL, BE, True,True)