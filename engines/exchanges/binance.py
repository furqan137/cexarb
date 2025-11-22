'''
    Binance Exchange Implementation
    Trading Fee: 0.1% (maker and taker)
    https://www.binance.com/en/fee/schedule
'''

from mod_imports import *
from base import *
from urllib.parse import urlencode
import asyncio

# import sys
# import os
# PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
# sys.path.insert(0, PROJECT_ROOT)

from engines.utils.check_asset_binance import binance_buy_token, binance_sell_token, binance_withdraw

class ExchangeEngine(ExchangeEngineBase):
    def __init__(self):
        self.API_URL = 'https://api.binance.us'
        self.apiVersion = 'v3'
        self.sleepTime = 5
        self.feeRatio = 0.005  # 0.1% trading fee
        self.basync = True
                  
    def _send_request(self, command, httpMethod, params={}, hook=None):          
        url = self.API_URL + command
        
        if httpMethod == "GET":
            R = grequests.get
        elif httpMethod == "POST":
            R = grequests.post
        elif httpMethod == "DELETE":
            R = grequests.delete
        
        headers = {}
                
        # Check if this is a signed request (not public endpoint)
        if not any(x in command for x in ['/api/v3/ticker', '/api/v3/depth', '/api/v3/time']):
            timestamp = str(int(1000 * time.time()))
            params['timestamp'] = timestamp
            
            # Create query string
            query_string = urlencode(params)
            
            # Sign the request
            secret = self.key['private']
            signature = hmac.new(secret.encode('utf8'), query_string.encode('utf8'), hashlib.sha256)
            signature = signature.hexdigest()
            
            params['signature'] = signature
            
            headers = {
                'X-MBX-APIKEY': self.key['public'],
            }
        
        args = {'headers': headers}
        if hook:
            args['hooks'] = dict(response=hook)
        
        if httpMethod == "GET" or httpMethod == "DELETE":
            args['params'] = params
        else:
            args['data'] = params
            
        req = R(url, **args)
        
        if self.basync:
            return req
        else:
            response = grequests.map([req])[0].json()
            return response
    
    '''
        return in r.parsed, showing all and required tickers
        {
            'XRP': 100.5,
            'USDT': 1000.0
        }
    '''    
    def get_balance(self, tickers=[]):
        return self._send_request('/api/v3/account', 'GET', {}, [self.hook_getBalance(tickers=tickers)])
    
    def hook_getBalance(self, *factory_args, **factory_kwargs):
        def res_hook(r, *r_args, **r_kwargs):
            json = r.json()
            r.parsed = {}
            
            if 'balances' in json:
                balances = json['balances']
                
                if factory_kwargs['tickers']:
                    balances = filter(lambda b: b['asset'].upper() in factory_kwargs['tickers'], balances)
                
                for balance in balances:
                    r.parsed[balance['asset'].upper()] = float(balance['free'])
                                  
        return res_hook    
    
    '''
        return USDT in r.parsed
        {
            'XRP': 0.5    
        }
    '''       
    def get_ticker_lastPrice(self, ticker):
         return self._send_request('/api/v3/ticker/price?symbol={0}USDT'.format(ticker), 'GET', {}, [self.hook_lastPrice(ticker=ticker)])

    def hook_lastPrice(self, *factory_args, **factory_kwargs):
        def res_hook(r, *r_args, **r_kwargs):
            json = r.json()
            r.parsed = {}
            if 'price' in json:
                r.parsed[factory_kwargs['ticker']] = float(json['price'])
                                  
        return res_hook    

    '''
        return in r.parsed
        {
            'bid': {
                'price': 0.5123,
                'amount': 1000.0
            },
            'ask': {
                'price': 0.5125,
                'amount': 500.0
            },           
        }
    '''       
    def get_ticker_orderBook_innermost(self, ticker):
        return self._send_request('/api/v3/depth?symbol={0}&limit=5'.format(ticker), 'GET', {}, self.hook_orderBook)     
     
    def hook_orderBook(self, r, *r_args, **r_kwargs):
        json = r.json()
        r.parsed = {
            'bid': {
                'price': float(json['bids'][0][0]),
                'amount': float(json['bids'][0][1])
            },
            'ask': {
                'price': float(json['asks'][0][0]),
                'amount': float(json['asks'][0][1])
            }
        }    
        
    '''
        return in r.parsed
        [
            {
                'orderId': '12345678',
                'created': '2024-01-01 00:00:00'
            }
        ]
    '''           
    def get_open_order(self):
        return self._send_request('/api/v3/openOrders', 'GET', {}, self.hook_openOrder)
    
    def hook_openOrder(self, r, *r_args, **r_kwargs):
        json = r.json()
        r.parsed = []
        if isinstance(json, list):
            for order in json:
                r.parsed.append({
                    'orderId': str(order['orderId']), 
                    'created': str(order['time'])
                })
        
    '''
        ticker: 'XRPUSDT'
        action: 'bid' or 'ask'
        amount: 100
        price: 0.5
    '''
    async def place_order(self, ticker, action, amount, price=None, market=False, quote_order_qty=False):
        side = 'BUY' if action == 'bid' else 'SELL'
        params = {'symbol': ticker, 'side': side}

        if market:
            # 🔹 Market order logic
            if quote_order_qty:
                # amount is in quote asset (e.g. USDT)
                return await binance_buy_token(self.key['public'], self.key['private'], amount, ticker)
            else:
                # amount is in base asset (e.g. BTC)
                return await binance_sell_token(self.key['public'], self.key['private'], amount, ticker)
        else:
            # 🔹 Limit order logic
            params['type'] = 'LIMIT'
            params['timeInForce'] = 'GTC'
            params['quantity'] = f"{amount:.5f}"
            params['price'] = f"{price:.5f}"

            print(f"params for binance : {params}")

            # Assuming _send_request is sync — wrap in thread if needed
            return await asyncio.to_thread(self._send_request, '/api/v3/order', 'POST', params)

    
    def cancel_order(self, orderID, ticker=''):
        params = {'orderId': orderID}
        if ticker:
            params['symbol'] = ticker
        return self._send_request('/api/v3/order', 'DELETE', params)
    
    def withdraw(self, ticker, amount, address, network=None, memo=None):
        """
        Withdraw crypto from Binance.US to another CEX or external wallet.

        Args:
            api_key (str): Binance API key
            api_secret (str): Binance API secret
            asset (str): e.g. 'USDT', 'BTC', 'ETH'
            address (str): destination wallet address
            amount (float): amount to withdraw
            network (str): optional, e.g. 'BSC', 'ETH', 'TRX'
            memo (str): optional (used for certain assets like XRP or XLM)

        Returns:
            dict: withdrawal response JSON
        """
        
        api_key = self.key["public"]
        api_secret = self.key["private"]
        
        return binance_withdraw(api_key, api_secret, ticker, address, amount, network, memo)
        
        base_url = "https://api.binance.us"
        endpoint = "/sapi/v1/capital/withdraw/apply"
        timestamp = int(time.time() * 1000)

        params = {
            "coin": ticker.upper(),
            "address": address,
            "amount": f"{amount:.8f}",
            "timestamp": timestamp,
        }
        if network:
            params["network"] = network
        if memo:
            params["addressTag"] = memo

        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

        url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
        headers = {"X-MBX-APIKEY": api_key}

        r = requests.post(url, headers=headers)
        try:
            r.raise_for_status()
            response = r.json()
            print("✅ Withdrawal request successful:", response)
            return response
        except Exception as e:
            print(f"❌ Withdrawal error: {e} → {r.text}")
            return {"error": str(e), "response": r.text}
    
    def get_deposit_address(self, coin):
        """
        Get deposit address for a specific coin.
        Returns a dictionary with 'address' and optional 'tag'.
        """
        params = {'coin': coin.upper()}
        r = self._send_request('/sapi/v1/capital/deposit/address', 'GET', params)
        
        # If asynchronous, map the request
        if self.basync:
            r = grequests.map([r])[0]

        json_data = r.json()
        if 'code' in json_data and json_data['code'] != 200:
            raise ValueError(f"Failed to get deposit address for {coin}: {json_data}")
        
        result = json_data.get('address') or json_data.get('result')  # Binance.US may differ in response
        tag = json_data.get('tag')  # For XRP or coins with memo/tag
        return {'address': result, 'tag': tag}

if __name__ == "__main__":
    engine = ExchangeEngine()
    engine.load_instance('keys/binance.key')
    print(f"address---------------")
    
    res = engine.get_deposit_address('XLM')
    print(f"depossit address : {res}")
    
    # Test examples
    # for res in grequests.map([engine.get_ticker_orderBook_innermost('XRPUSDT')]):
    #     print res.parsed
    #     pass
    # for res in grequests.map([engine.get_ticker_lastPrice('XRP')]):
    #     print res.parsed
    #     pass
    # for res in grequests.map([engine.get_balance(['XRP', 'USDT'])]):
    #     print res.parsed
    #     pass
    import time
    import hmac
    import hashlib
    import requests

    # Binance.US API credentials
    api_key = "dsIJAWTBB0gezwo75sFG5mcZPN2gFN6S5D7t1v8xyigp8pLxiJClnCLstcqlsekY".strip()
    api_secret = "YPgwiRF3IjzXuXVffnKHeRhWQCpcH2LPCg68ZgoUQtWXlglOBpRxRU4mpnlzGatQ".strip()

    # Binance.US base URL
    BASE_URL = "https://api.binance.us"

    # Current timestamp in milliseconds
    ts = int(time.time() * 1000)
    params = {"timestamp": ts}

    # Create query string and signature
    query_string = "&".join(f"{k}={params[k]}" for k in sorted(params))
    signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature

    # Request headers
    headers = {"X-MBX-APIKEY": api_key}

    # Send request to Binance.US account endpoint
    r = requests.get(f"{BASE_URL}/api/v3/account", headers=headers, params=params)

    print(r.status_code, r.json())