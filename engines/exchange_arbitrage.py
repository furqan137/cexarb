import os
import time
from time import strftime
import grequests
from engines.exchanges.loader import EngineLoader
from engines.utils.total_asset_volume import total_usdt_across_all
import asyncio

class CryptoEngineExArbitrage(object):
    def __init__(self, exParams, mock=False):
        self.exParams = exParams
        self.mock = mock
        self.minProfit = 0.0001 # This may not be accurate as coins have different value        
        self.hasOpenOrder = True # always assume there are open orders first
        self.openOrderCheckCount = 0

        self.engineA = EngineLoader.getEngine(self.exParams['exchangeA']['exchange'], self.exParams['exchangeA']['keyFile'])
        self.engineB = EngineLoader.getEngine(self.exParams['exchangeB']['exchange'], self.exParams['exchangeB']['keyFile'])
        # self.engineC = EngineLoader.getEngine(self.exParams['exchangeC']['exchange'], self.exParams['exchangeC']['keyFile'])

    async def start_engine(self):
        print(strftime('%Y%m%d%H%M%S') + ' starting Exchange Arbitrage Engine...')
        if self.mock:
            print('1---------------------------- MOCK MODE ----------------------------')
        #Send the request asynchronously
        while True:
            try:
                # if not self.mock and self.hasOpenOrder:
                #     self.check_openOrder()
                # else:
                    # if self.check_balance():
                    #     print(f"<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
                    #     bookStatus = self.check_orderBook()
                    #     if bookStatus['status']:
                    #         self.place_order(bookStatus['status'], bookStatus['ask'], bookStatus['bid'], bookStatus['maxAmount'])
                    # else:
                    #     self.rebalance()
                success = await self.start_engine_direct_arb_balance_preserving()
            except Exception as e:
                print(e)

            if success:
                time.sleep(120)
            else:
                time.sleep(self.engineA.sleepTime)
            
    async def start_engine_direct_arb_balance_preserving(self):
        """
        Direct arbitrage with balance-preserving logic for 3 exchanges:
        Binance (B), Kraken (A), Crypto.com (C)
        Buy from cheapest exchange and sell on most expensive exchange,
        then transfer purchased tokens back to the expensive exchange.
        """
        
        # 1. Fetch last prices
        rs = [
            self.engineA.get_ticker_lastPrice(self.exParams['exchangeA']['tickerB']),
            self.engineB.get_ticker_lastPrice(self.exParams['exchangeB']['tickerB']),
            # self.engineC.get_ticker_lastPrice(self.exParams['exchangeC']['tickerB'])
        ]
        
        responses = self.send_request(rs)     
        priceA = responses[0].parsed[self.exParams['exchangeA']['tickerB']]
        priceB = responses[1].parsed[self.exParams['exchangeB']['tickerB']]

        prices = {
            'A': priceA,
            'B': priceB,
            # 'C': responses[2].parsed[self.exParams['exchangeC']['tickerB']]
        }

        ex_names = {
            'A': self.exParams['exchangeA']['exchange'],
            'B': self.exParams['exchangeB']['exchange'],
            # 'C': self.exParams['exchangeC']['exchange']
        }
        
        # -----------------------
        # 💾 Log prices to a file
        # -----------------------
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "price_log.txt")
        timestamp = strftime('%Y-%m-%d %H:%M:%S')
        #check if there is profit
        
        with open(log_path, "a") as f:
            # f.write(f"{timestamp} | {ex_names['A']}: {prices['A']:.6f} | {ex_names['B']}: {prices['B']:.6f} | {ex_names['C']}: {prices['C']:.6f}\n")
            f.write(f"{timestamp} | {ex_names['A']}: {prices['A']:.6f} | {ex_names['B']}: {prices['B']:.6f}\n")

        # 2. Determine cheapest and most expensive exchange
        price_list = [(k, v) for k, v in prices.items()]
        price_list.sort(key=lambda x: x[1])  # ascending

        cheapest_key, cheap_price = price_list[0]
        expensive_key, expensive_price = price_list[-1]

        cheap_engine = getattr(self, f"engine{cheapest_key}")
        expensive_engine = getattr(self, f"engine{expensive_key}")

        cheap_pair = self.exParams[f"exchange{cheapest_key}"]['tickerPair']
        expensive_pair = self.exParams[f"exchange{expensive_key}"]['tickerPair']
        token = self.exParams[f"exchange{expensive_key}"]['tickerB']
        base_token = self.exParams[f"exchange{cheapest_key}"]['tickerA']        

        # 3. Fetch order books
        # print(f"pairs - cheap: {cheap_pair}, expensive: {expensive_pair}")
        # cheap_order_book = grequests.map([cheap_engine.get_ticker_orderBook_innermost(cheap_pair)])[0].parsed
        # print("1===============")
        # expensive_order_book = grequests.map([expensive_engine.get_ticker_orderBook_innermost(expensive_pair)])[0].parsed
        # print("2===============")
        # 4. Fetch balances
        cheap_bal_req = cheap_engine.get_balance([base_token])
        exp_bal_req = expensive_engine.get_balance([token])
        cheap_bal_res = grequests.map([cheap_bal_req])[0]
        exp_bal_res = grequests.map([exp_bal_req])[0]

        cheap_balance = cheap_bal_res.parsed.get(base_token.upper(), 0.0)
        exp_balance = exp_bal_res.parsed.get(token.upper(), 0.0)        

        # 5. Compute maximum tradable amount
        # Buy using 1/5 of cheap base balance (e.g., 1/5 of available USDT)
        buy_budget = cheap_balance / 3.0

        # Effective price to buy one token on cheap exchange
        buy_price = cheap_price
        buy_fee = 1 + cheap_engine.feeRatio

        # Calculate how many tokens we can buy with 1/5 of balance (after fees)
        buy_amount = buy_budget / (buy_fee * buy_price)

        # The sell amount must match the buy amount
        sell_amount = buy_amount

        # Make sure we don’t exceed what we can actually sell
        sell_fee = 1 + expensive_engine.feeRatio
        sell_price = expensive_price

        # Convert exp_balance (token balance) into tradable amount limit
        max_sellable_amount = exp_balance / sell_fee

        # Final maximum tradable amount = min of what we can buy and sell
        max_amount = min(buy_amount, max_sellable_amount)
        
        if max_amount <= 0:
            print(f"Not enough liquidity or balance for arbitrage : {max_amount}")
            return

        ask_price = cheap_price
        bid_price = expensive_price

        # 6. Calculate net profit
        fee_total = max_amount * cheap_price * cheap_engine.feeRatio + max_amount * expensive_price * expensive_engine.feeRatio
        gross_profit = max_amount * (expensive_price - cheap_price)
        net_profit = gross_profit - fee_total

        deposit_USDT_cheap = cheap_engine.get_deposit_address("USDT")
        deposit_USDT_expensive = expensive_engine.get_deposit_address("USDT")
        deposit_address_usdt = deposit_USDT_cheap['address']

        deposit_info_cheap = cheap_engine.get_deposit_address(token)
        deposit_info_expensive = expensive_engine.get_deposit_address(token)
        deposit_address_token = deposit_info_expensive['address']
        deposit_tag_token = deposit_info_expensive['tag']
        # print(f"Deposit address on {cheap_engine.key['exchange']}: {deposit_USDT_cheap}")
        # print(f"Deposit address on {expensive_engine.key['exchange']}: {deposit_USDT_expensive}")

        if self.openOrderCheckCount == 0:
            print(f"{strftime('%Y%m%d%H%M%S')} : Cheapest: {ex_names[cheapest_key]} {cheap_price}, Expensive: {ex_names[expensive_key]} {expensive_price}")
        elif self.openOrderCheckCount == 20:
            self.openOrderCheckCount = -1
        self.openOrderCheckCount += 1

        print("=" * 50)
        print(strftime('%Y%m%d%H%M%S') + ' starting exchange Balance-Preserving Direct Arbitrage Engine...')
        
        print(f"token : {token}, base_token : {base_token}")
        print(f"Cheapest: {ex_names[cheapest_key]} {cheap_price}, Expensive: {ex_names[expensive_key]} {expensive_price}")
        print(f"Balances - {cheap_engine.key['exchange']} {base_token}: {cheap_balance}, {expensive_engine.key['exchange']} {token}: {exp_balance}")
        print(f"buy amount : {buy_amount}, sell amount : {sell_amount}")
        print(f"cheap fee : {cheap_engine.feeRatio}, expense fee : {expensive_engine.feeRatio}")
        print(f"Arbitrage amount: {max_amount:.6f} {token}")
        print(f"Gross profit: {gross_profit:.6f}, Fees: {fee_total:.6f}, Net profit: {net_profit:.6f}")        

        if net_profit <= self.minProfit:
            # print("Not profitable after fees and slippage, skipping orders")
            return

        success = False

# 7. Place orders
        if not self.mock:           
            try:
                print(f"Placing BUY on {cheap_engine.key['exchange']} and SELL on {expensive_engine.key['exchange']}")

                # 🔹 Run both buy and sell orders concurrently
                if cheap_engine.key['exchange'].lower() in ['binance', 'okx']:
                    buy_task = cheap_engine.place_order(
                        cheap_pair, 'bid', max_amount * cheap_price, market=True, quote_order_qty=True
                    )
                else:
                    buy_task = cheap_engine.place_order(
                        cheap_pair, 'bid', max_amount, market=True
                    )

                sell_task = expensive_engine.place_order(
                    expensive_pair, 'ask', max_amount, market=True
                )

                # 🔹 Run both orders at the same time
                sell_order, buy_order = await asyncio.gather(sell_task, buy_task)
                print(f"Buy and Sell orders placed successfully! Buy: {buy_order}, Sell: {sell_order}")

                # 8. Transfer purchased tokens back to expensive exchange
                # print(f"Transferring {max_amount:.6f} {token} from {cheap_engine.key['exchange']} to {expensive_engine.key['exchange']} at address {deposit_address}")
                
                withdraw_response = cheap_engine.withdraw(token, max_amount, deposit_address_token, token, deposit_tag_token)
                print(f"Withdrawal initiated successfully: {withdraw_response}")
                
                # withdraw_response = cheap_engine.withdraw("USDT", 12, deposit_address_usdt, "ETH", None)
                # print(f"Withdrawal initiated successfully: {withdraw_response}")

                total_val_usdt = total_usdt_across_all()
                print(f"Total USDT value across exchanges after arbitrage: {total_val_usdt:.2f} USDT")

                success = True

            except Exception as e:
                print(f"❌ Error during arbitrage execution: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
            print("=" * 50)

        print("Balance-preserving direct arbitrage executed successfully across 3 exchanges")
        
        return success

            
    def check_openOrder(self):
        if self.openOrderCheckCount >= 5:
            self.cancel_allOrders()
        else:
            print('checking open orders...')
            rs = [self.engineA.get_open_order(),
                  self.engineB.get_open_order()]
            responses = self.send_request(rs)

            if not responses[0] or not responses[1]:
                print(responses)
                return False
            
            if responses[0].parsed or responses[1].parsed:
                self.engineA.openOrders = responses[0].parsed
                self.engineB.openOrders = responses[1].parsed
                print(self.engineA.openOrders, self.engineB.openOrders)
                self.openOrderCheckCount += 1
            else:
                self.hasOpenOrder = False
                print('no open orders')
                print('starting to check order book...')
    
    def cancel_allOrders(self):
        print('cancelling all open orders...')
        rs = []
        print(self.exParams['exchangeA']['exchange'])
        for order in self.engineA.openOrders:
            print(order)
            rs.append(self.engineA.cancel_order(order['orderId']))

        print(self.exParams['exchangeB']['exchange'])
        for order in self.engineB.openOrders:
            print(order)
            rs.append(self.engineB.cancel_order(order['orderId']))

        responses = self.send_request(rs)
        
        self.engineA.openOrders = []
        self.engineB.openOrders = []
        self.hasOpenOrder = False
        

    #Check and set current balance
    def check_balance(self):
        print(f'1.checking balance... : {self.exParams}')
        rs = [self.engineA.get_balance([self.exParams['exchangeA']['tickerA'], self.exParams['exchangeA']['tickerB']]),
              self.engineB.get_balance([self.exParams['exchangeB']['tickerA'], self.exParams['exchangeB']['tickerB']])]

        print(f"Get balance requests sent: {rs}")
        print('2.checking balance...')
        responses = self.send_request(rs)

        self.engineA.balance = responses[0].parsed
        self.engineB.balance = responses[1].parsed
        
        print(f'Balances:{self.engineA.balance}, {self.engineB.balance}')
        
        if not self.mock:
            for res in responses:
                for ticker in res.parsed:
                    # This may not be accurate
                    if res.parsed[ticker] < 0.05:
                        print(ticker, res.parsed[ticker], '- Not Enough')
                        return False
        return True
    
    def rebalance(self):
        print('rebalancing...')

    def check_orderBook(self):
        rs = [self.engineA.get_ticker_orderBook_innermost(self.exParams['exchangeA']['tickerPair']),
              self.engineB.get_ticker_orderBook_innermost(self.exParams['exchangeB']['tickerPair'])]

        responses = self.send_request(rs)
        
        print("silver : {0} - {1}; {2} - {3}".format(
            self.exParams['exchangeA']['exchange'],
            responses[0].parsed,
            self.exParams['exchangeB']['exchange'],
            responses[1].parsed
            ))

        diff_A = responses[0].parsed['ask']['price'] - responses[1].parsed['bid']['price']
        diff_B = responses[1].parsed['ask']['price'] - responses[0].parsed['bid']['price']
        if diff_A < 0 and diff_B < 0 and abs(diff_A) < abs(diff_B):
            diff_A = 0
        # Buy from Exchange A, Sell to Exchange B
        print(f"diff_A: {diff_A}, diff_B: {diff_B}")
        if diff_A < 0:
            maxAmount = self.getMaxAmount(responses[0].parsed['ask'], responses[1].parsed['bid'], 1)
            fee = self.engineA.feeRatio * maxAmount * responses[0].parsed['ask']['price'] + self.engineB.feeRatio * maxAmount * responses[1].parsed['bid']['price']

            if abs(diff_A * maxAmount) - fee > self.minProfit:
                print("{0}'s Ask {1} - {2}'s Bid {3} < 0".format(
                    self.exParams['exchangeA']['exchange'], 
                    responses[0].parsed['ask']['price'],
                    self.exParams['exchangeB']['exchange'], 
                    responses[1].parsed['bid']['price']))       
                print('{0} (diff) * {1} (amount) = {2}, commission fee: {3}'.format(diff_A, maxAmount, abs(diff_A * maxAmount), fee))            
                return {'status': 1, 'ask': responses[0].parsed['ask']['price'], 'bid': responses[1].parsed['bid']['price'], 'maxAmount': maxAmount}
            else:
                return {'status': 0}

        # Buy from Exchange B, Sell to Exchange A
        elif diff_B < 0:
            maxAmount = self.getMaxAmount(responses[1].parsed['ask'], responses[0].parsed['bid'], 2)
            fee = self.engineB.feeRatio * maxAmount * responses[1].parsed['ask']['price'] + self.engineA.feeRatio * maxAmount * responses[0].parsed['bid']['price']

            if abs(diff_B * maxAmount) - fee > self.minProfit:
                print("{0}'s Ask {1} - {2}'s Bid {3} < 0".format(
                    self.exParams['exchangeB']['exchange'], 
                    responses[1].parsed['ask']['price'], 
                    self.exParams['exchangeA']['exchange'], 
                    responses[0].parsed['bid']['price']))             
                print('{0} (diff) * {1} (amount) = {2}, commission fee: {3}'.format(diff_B, maxAmount, abs(diff_B * maxAmount), fee))   
                return {'status': 2, 'ask': responses[1].parsed['ask']['price'], 'bid': responses[0].parsed['bid']['price'], 'maxAmount': maxAmount}
            else:
                return {'status': 0}

        return {'status': 0}

    def getMaxAmount(self, askOrder, bidOrder, type):
        amount = 0
        # Buy from Exchange A, Sell to Exchange B
        if type == 1:
            maxOwnAmountA = self.engineA.balance[self.exParams['exchangeA']['tickerA']] / ((1 + self.engineA.feeRatio) * askOrder['price'])
            maxOwnAmountB = self.engineB.balance[self.exParams['exchangeB']['tickerB']]
            amount = min(maxOwnAmountA, maxOwnAmountB, askOrder['amount'], bidOrder['amount'])
        # Buy from Exchange B, Sell to Exchange A
        elif type == 2:
            maxOwnAmountA = self.engineA.balance[self.exParams['exchangeA']['tickerB']]
            maxOwnAmountB = self.engineB.balance[self.exParams['exchangeB']['tickerA']] / ((1 + self.engineB.feeRatio) * askOrder['price'])
            amount = min(maxOwnAmountA, maxOwnAmountB, askOrder['amount'], bidOrder['amount'])

        return amount

    def place_order(self, status, ask, bid, amount):
        print('placing order...')
        # Buy from Exchange A, Sell to Exchange B                
        if status == 1:
            print(strftime('%Y%m%d%H%M%S') + ' Buy at {0} @ {1} & Sell at {2} @ {3} for {4}'.format(ask, self.exParams['exchangeA']['exchange'], bid, self.exParams['exchangeB']['exchange'], amount))
            rs = [
                self.engineA.place_order(self.exParams['exchangeA']['tickerPair'], 'bid', amount, ask),
                self.engineB.place_order(self.exParams['exchangeB']['tickerPair'], 'ask', amount, bid),                
            ]
        # Buy from Exchange B, Sell to Exchange A
        elif status == 2:
            print(strftime('%Y%m%d%H%M%S') + ' Buy at {0} @ {1} & Sell at {2} @ {3} for {4}'.format(ask, self.exParams['exchangeB']['exchange'], bid, self.exParams['exchangeA']['exchange'], amount))
            rs = [
                self.engineB.place_order(self.exParams['exchangeB']['tickerPair'], 'bid', amount, ask),
                self.engineA.place_order(self.exParams['exchangeA']['tickerPair'], 'ask', amount, bid),                
            ]

        if not self.mock:
            responses = self.send_request(rs)
        self.hasOpenOrder = True
        self.openOrderCheckCount = 0

    def send_request(self, rs):
        responses = grequests.map(rs)
        for res in responses:
            if not res:                
                print(responses)
                raise Exception
        return responses

    def run(self):
        asyncio.run(self.start_engine())

if __name__ == '__main__':
    
    total_usdt_across_all()
    # exParams = {
    #     'exchangeA': {
    #         'exchange': 'kraken',
    #         'keyFile': '../keys/kraken.key',
    #         'tickerPair': 'XRPUSDT',  # Kraken uses XRPUSDT format
    #         'tickerA': 'BTC',
    #         'tickerB': 'XXRP'  # Kraken uses XXRP for XRP
    #     },
    #     'exchangeB': {
    #         'exchange': 'binance',
    #         'keyFile': '../keys/binance.key',
    #         'tickerPair': 'XRPUSDT',  # Binance uses XRPUSDT format
    #         'tickerA': 'BTC',
    #         'tickerB': 'XRP'
    #     }
    # }
    # # Run in mock mode (True) for testing without real trades
    # engine = CryptoEngineExArbitrage(exParams, True)
    # # Uncomment below to run with real trading (use with caution!)
    # #engine = CryptoEngineExArbitrage(exParams)
    # engine.run()
