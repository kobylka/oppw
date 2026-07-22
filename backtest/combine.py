from datetime import datetime, timedelta
import os
import matplotlib.pyplot as plt
import numpy as np
import math

quotes = {}

wallet = {}
stocks = []
transactions = []
balance = 0
deposited = 0
transaction_n = 0
timeouts = 0
profits = 0
gained = 0

LEVERAGE = 3

def add_days(date, D):
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    new_date = date_obj + timedelta(days=D)
    new_date = new_date.strftime("%Y-%m-%d")
    return new_date
    
def date_diff(date_str1, date_str2):
    # Convert the date strings to datetime objects
    date1 = datetime.strptime(date_str1, '%Y%m%d')
    date2 = datetime.strptime(date_str2, '%Y%m%d')

    # Calculate the difference in days
    return (date2 - date1).days
    
def process_buy_transaction(date, stock, current_price, amount):
    global balance,deposited,LEVERAGE
    new_shares = round(int(1000000*amount / current_price - 1)/1000000, 6)*LEVERAGE
    new_price = round((new_shares * current_price + wallet[stock][0] * wallet[stock][1]) / (new_shares + wallet[stock][0]), 4)
    DAT  = date
    if(wallet[stock][3] != 0): DAT = wallet[stock][3]
    wallet[stock] = [round(new_shares  + wallet[stock][0], 6), new_price, current_price, DAT]
    balance = round(balance - new_shares * current_price/LEVERAGE, 2)
    #print(date,balance)
    record_transaction(date, stock, new_shares, wallet[stock][0], current_price, new_price)
    
def process_all_sell_transaction(date, stock, current_price):
    global balance,gained,LEVERAGE
    shares = wallet[stock][0]
    avg_price = wallet[stock][1]
    gained += shares*current_price - shares*avg_price
    wallet[stock] = [0, 0, 0, 0]
    #print(date,(shares * avg_price)*(current_price/avg_price-1))
    balance = round(balance + (shares * avg_price)*(current_price/avg_price-1)+shares*avg_price/LEVERAGE, 2)
    record_transaction(date, stock, -shares, wallet[stock][0], current_price, wallet[stock][1])
    
def record_transaction(date, stock, share, tot, current_price, avg_price):
    global balance
    transactions.append({
        'date': date,
        'stock': stock,
        'share': share,
        'tot': tot,
        'current_price': current_price,
        'avg_price': avg_price
    })
    action = "Buy" if share > 0 else "Sell"
    #print(f"{action}: {date}, Stock: {stock}, Shares: {round(share, 3)}, Total Shares: {round(tot, 3)}, Price: {current_price}, Avg Price: {avg_price}, Balance: {round(balance, 2)}, Total Value: {round(tot * current_price, 2)}, Deposited: {deposited}")

def read_quotes(files, start_date):
    quotes = {}
    for f in files:
        fname = f.split(".")
        if fname[-1] == "txt":
            stock = fname[0].upper()
            stocks.append(stock)
            wallet[stock] = [0,0,0,0]
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
                    
                    if date not in quotes:
                        quotes[date] = {}

                    quotes[date][stock] = [opon, high, low, close]
    
    return quotes
    
def print_wallet(end_date,WIN_RATE, MAX_DD, debug,MAX_AMOUNT, PROFIT_FACTOR,TIMEOUT,SL):
    global balance
    total_wallet_value = balance
    total_wallet_initial = 0
    # Calculate and print wallet contents sorted by total value of shares
    wallet_value = {}
    for stock, data in wallet.items():
        shares = data[0]  # Number of shares
        if(shares == 0):
            continue
        current_price = 0
        if(stock in quotes[end_date]):
            current_price = quotes[end_date][stock][0]  # Current price
        else:
            print(stock,"WTF")
                
        total_value = shares * current_price if shares > 0 else 0  # Calculate total value
        wallet_value[stock] = total_value
        total_wallet_value += total_value
        total_wallet_initial += wallet[stock][0] * wallet[stock][1]

    # Sort wallet by total value in descending order
    sorted_wallet = sorted(wallet_value.items(), key=lambda x: x[1], reverse=True)
    
    first = 0
    if(debug is True):
        print("\nWallet Contents Sorted by Total Value of Shares:")
    for stock, value in sorted_wallet:
        shares = wallet[stock][0]
        avg_price = wallet[stock][1]
        if(first == 0):
            first = value
        if(debug is True):
            if(stock in quotes[end_date]):
                if(wallet[stock][0] > 0 and quotes[end_date][stock][0] < avg_price):
                    print(f"LOSS {stock}, Shares: {shares}, Avg Price: {avg_price}, Last Price: {quotes[end_date][stock][0]}, Total Value: {value:.2f}, {wallet[stock][3]}")
                elif(wallet[stock][0] > 0):
                    print(f"{stock}, Shares: {shares}, Avg Price: {avg_price}, Last Price: {quotes[end_date][stock][0]}, Total Value: {value:.2f}, {wallet[stock][3]}")
            

    print(WIN_RATE, round(MAX_DD,1), int(MAX_AMOUNT), round(total_wallet_value), round(deposited), round(total_wallet_value/deposited, 3),round(MAX_AMOUNT))

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
    
def process(quotes, stock, start_date, end_date, TIMEOUT, SL, debug, plots):
    global balance,deposited,profits,transaction_n,timeouts,gained,LEVERAGE
    
    prev_date = "20000101"
    prev_depo = "20000101"
    prev_year = start_date
    next_price = 0
    init = False
    
    N_STOCKS = 1
    MAX_EQUITY = 1
    MAX_DD = 100
    
    equity_history = []
    deposit_history = []
    
    yearlies = []
        
    initial   = 10000
    deposited = initial
    balance   = initial
    
    prev_equity = initial
    
    equity = 0
    
    WIN = 0
    LOSS = 0
    
    WIN_AMOUNT = 0
    LOSS_AMOUNT = 1
    
    prev_close = 0
    prev_open = 0
    
    sma_list = []
    sma = 0
    sma_len = 200
    
    prev_price = 1
    
    ret_equity = 0
    
    gained = 0
    
    IBS = 1
    IBS_PREV = 1
        
    L_prev = 0
    C_prev = 0
    
    open_price = 0
    break_even = False
    
    n = 0
    m = 0
    i=0
    j=0
    
    TP = 0.022
    SL = 0.9166
    BE = 0.997
    
    LEVERAGE = 6
    
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
        is_thursday = date_obj.weekday() == 3
        
        opon = quotes[date][stock][0]
        high = quotes[date][stock][1]
        low  = quotes[date][stock][2]
        close = quotes[date][stock][3]
        
        #if(balance < initial):
            #deposited += initial-balance
            #balance += initial-balance
            
        if(date_diff(prev_date, date) > 1 and (is_monday is True or is_tuesday is True)):
            if(open_price > 0):
                close_price = quotes[prev_date][stock][3]
                change = round(close_price/open_price-1,4)
                balance += balance*change*LEVERAGE
                #if(change < 0):
                #    balance += 3000
                 #   deposited += 3000
                print("T", open_date, prev_date, change)
                change = 0
                open_date = ""
        
                equity_history.append(balance)
                deposit_history.append(deposited)
            else:
                open_price = opon
                open_date  = date
                break_even = False
                i+=1
            
            #if(change > TP): 
                #print(i,change,balance, balance*change*5)
                
            #print(i,change,balance, balance*change)
        elif(open_price > 0):
            if(break_even == True):
                if(date_obj.weekday() == 1): print(date_obj.weekday())
                if(opon > open_price*BE):
                    close_price = opon
                    change = round(close_price/open_price-1,4)
                    balance += balance*change*LEVERAGE
                    print("O", open_date, date, change)
                    change = 0
                    open_price = 0
                    j+=1
                    break_even = False
                    equity_history.append(balance)
                    deposit_history.append(deposited)
                elif(high > open_price*BE):
                    close_price = open_price*BE
                    close_price = open_price*BE
                    change = round(close_price/open_price-1,4)
                    balance += balance*change*LEVERAGE
                    j+=1
                    equity_history.append(balance)
                    deposit_history.append(deposited)
                    print("B", open_date, date, change)
                    change = 0
                    open_price = 0
                    break_even = False
        
            if(close < open_price*BE):
                #print("D", open_date, date, close, open_price)
                break_even = True
            if(open_price*SL > opon):
                close_price = opon
                change = round(close_price/open_price-1,4)
                balance += balance*change*LEVERAGE
                print("FUCK", open_date, date, change)
                change = 0
                open_price = 0
                j+=1
                break_even = False
                
                equity_history.append(balance)
                deposit_history.append(deposited)
        if(open_price*SL > low):
                close_price = open_price*SL
                change = round(close_price/open_price-1,4)
                balance += balance*change*LEVERAGE
                print("SL", open_date, date, change)
                change = 0
                open_price = 0
                j+=1
                break_even = False
                
                equity_history.append(balance)
                deposit_history.append(deposited)
        elif(opon > open_price*(1+TP) and open_price > 0):
                close_price = opon
                change = round(close_price/open_price-1,4)
                balance += balance*change*LEVERAGE
                print("OH", open_date, date, change)
                change = 0
                open_price = 0
                
                equity_history.append(balance)
                deposit_history.append(deposited)
        elif(close > open_price*(1+TP) and open_price > 0):
                close_price = close
                change = round(close_price/open_price-1,4)
                balance += balance*change*LEVERAGE
                print("CH", open_date, date, change)
                change = 0
                open_price = 0
                
                equity_history.append(balance)
                deposit_history.append(deposited)
        prev_date = date
        
        #print(change)
        
        if(balance < 10000):
            deposited += 10000-balance
            balance += 10000-balance
        
        if(equity > 300000000):
            ret_equity = equity
            
            for stock in wallet:
                wallet[stock] = [0,0,0,0]
                balance = 0
                deposited = 0
                transaction_n = 0
                timeouts = 0
                profits = 0
                equity_history = 0
                
            return [date_diff(start_date, date), date, ret_equity]
           
    
    #print(yearlies)
    print(deposited,balance,TIMEOUT,SL,WIN+LOSS,end=" ")
    #print_wallet(end_date, round(WIN/(WIN+LOSS), 2), 100*(1-MAX_DD),debug,MAX_EQUITY,WIN_AMOUNT/LOSS_AMOUNT,TIMEOUT,SL)
    if(plots == True):
        plotting(equity_history, deposit_history)
    
    ret_equity = equity
    ret_balance = balance
    
    for stock in wallet:
        wallet[stock] = [0,0,0,0]
        balance = 0
        equity = 0
        deposited = 0
        equity_history = 0
        transaction_n = 0
        timeouts = 0
        profits = 0
    
    return [0, date, ret_balance]
    
if __name__ == "__main__":
    files = os.listdir()
    
    #start_date = "20181016"
    #start_date = "20000104"
    #start_date = "20000103"
    start_date = "20100104"
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
    end_date = "20200102"
    #end_date = "20251017"
    #end_date = "20160104"
    #end_date = "20190201"
    #end_date = "20230103"
    #end_date = "20200102"
    #end_date = "20120103"
    #end_date = "20111230"
    #end_date = "20191231"
    #end_date = "20221230"
    
    quotes = read_quotes(files, start_date)
    #for f in files:
    #    print(f, end=" ")    
    #    process(quotes, f.split(".")[0].upper(), start_date, end_date, 0.1,0.9,30,0.0,False,False)
    
    values = 0
    suma = 0
    n=0
    prev_date = start_date
    stock = "QLD"
    quote = []
    for date in quote:
        if date == end_date: break
        if stock in quotes[date]:
            if(prev_date[4:6] != date[4:6]):
                original_date = datetime.strptime(date, "%Y%m%d")
                ending_date = original_date.replace(year=original_date.year + 5)
                ending_date_str = ending_date.strftime("%Y%m%d")
                if(ending_date_str not in quotes):
                    ending_date = ending_date.replace(day=ending_date.day + 1)
                    ending_date_str = ending_date.strftime("%Y%m%d")
                if(ending_date_str not in quotes):
                    ending_date = ending_date.replace(day=ending_date.day + 1)
                    ending_date_str = ending_date.strftime("%Y%m%d")
                result = process(quotes, stock, date, ending_date_str,999,0.09875,False,False)
                print(date, round(result[0]/365,2), result[1], result[2])
                values += result[2]
                if(result[0] > 0):
                    suma += result[0]/365
                n+=1
                prev_date = date
    
    result = process(quotes, "QQQ", start_date, end_date, 14,0.09,False,True)
    
    if(n>0):print(suma/n, values/n)
    
    #C<L
    