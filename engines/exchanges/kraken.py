import time
import hmac
import hashlib
import base64
import urllib.parse
import calendar
import grequests
import requests
import socket
import requests.packages.urllib3.util.connection as urllib3_conn
from datetime import datetime, timedelta
from mod_imports import *

import sys
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.insert(0, PROJECT_ROOT)

from engines.token_helper import buy_token_kraken, sell_token_kraken

# -------------------------------------------------------------------
# FORCE IPv4 CONNECTIONS (Kraken rejects IPv6 for some endpoints)
# -------------------------------------------------------------------
def _force_ipv4():
    def allowed_gai_family():
        return socket.AF_INET  # Force IPv4 only
    urllib3_conn.allowed_gai_family = allowed_gai_family

_force_ipv4()


# -------------------------------------------------------------------
# KRAKEN EXCHANGE ENGINE
# -------------------------------------------------------------------
class ExchangeEngine(ExchangeEngineBase):
    def __init__(self):
        self.API_URL = 'https://api.kraken.com'
        self.apiVersion = '0'
        self.feeRatio = 0.001
        self.sleepTime = 5
        self.basync = True

    # -----------------------
    # Core HTTP Request Sender
    # -----------------------
    def _send_request(self, command, httpMethod, params={}, hook=None):
        command_path = '/{0}/{1}'.format(self.apiVersion, command)
        url = self.API_URL + command_path

        if httpMethod.upper() == "GET":
            R = grequests.get
        elif httpMethod.upper() == "POST":
            R = grequests.post
        else:
            raise ValueError("Unsupported HTTP method")

        headers = {}
        # For private API endpoints (require auth)
        if not any(x in command_path.lower() for x in ['public']):
            secret = self.key['private']
            params['nonce'] = int(1000 * time.time())

            nonce_str = str(params['nonce'])
            postdata = urllib.parse.urlencode(params)
            encoded_postdata = (nonce_str + postdata).encode('utf-8')

            message = command_path.encode('utf-8') + hashlib.sha256(encoded_postdata).digest()
            signature = hmac.new(base64.b64decode(secret), message, hashlib.sha512)

            headers = {
                'API-Key': self.key['public'],
                'API-Sign': base64.b64encode(signature.digest()),
                'Host': 'api.kraken.com'  # Ensure correct host header for IPv4
            }

        args = {'data': params, 'headers': headers}
        if hook:
            args['hooks'] = dict(response=hook)

        req = R(url, **args)
        if self.basync:
            return req
        else:
            response = grequests.map([req])[0].json()
            return response

    # -----------------------
    # Account Balance
    # -----------------------
    def get_balance(self, tickers=[]):
        return self._send_request('private/Balance', 'POST', {}, [self.hook_getBalance(tickers=tickers)])

    def hook_getBalance(self, *factory_args, **factory_kwargs):
        def res_hook(r, *_, **__):
            json_data = r.json()
            r.parsed = {}

            if json_data.get("error"):
                print("Kraken API Error:", json_data["error"])
                return

            balances = json_data.get("result", {})
            tickers_filter = [t.upper() for t in factory_kwargs.get('tickers', [])]

            for ticker, value in balances.items():
                norm = ticker.upper()
                if norm.startswith('X') or norm.startswith('Z'):
                    norm = norm[1:]
                if not tickers_filter or norm in tickers_filter:
                    r.parsed[norm] = float(value)
        return res_hook

    # -----------------------
    # Order Book (best bid/ask)
    # -----------------------
    def get_ticker_orderBook_innermost(self, ticker):
        return self._send_request(f'public/Depth?pair={ticker}&count=1', 'GET', {}, self.hook_orderBook)

    def hook_orderBook(self, r, *_, **__):
        json_data = r.json()
        ticker = next(iter(json_data['result']))
        result = json_data['result'][ticker]
        r.parsed = {
            'bid': {
                'price': float(result['bids'][0][0]),
                'amount': float(result['bids'][0][1])
            },
            'ask': {
                'price': float(result['asks'][0][0]),
                'amount': float(result['asks'][0][1])
            }
        }

    # -----------------------
    # Open Orders
    # -----------------------
    def get_open_order(self):
        return self._send_request('private/OpenOrders', 'POST', {}, self.hook_openOrder)

    def hook_openOrder(self, r, *_, **__):
        json_data = r.json()
        r.parsed = []
        for order_id, order in json_data.get('result', {}).get('open', {}).items():
            r.parsed.append({'orderId': order_id, 'created': order['opentm']})

    # -----------------------
    # Cancel an Order
    # -----------------------
    def cancel_order(self, orderID):
        return self._send_request('private/CancelOrder', 'POST', {'txid': orderID})

    # -----------------------
    # Withdraw
    # -----------------------
    def withdraw(self, ticker, withdrawalKey, amount):
        return self._send_request('private/Withdraw', 'POST', {'asset': ticker, 'key': withdrawalKey, 'amount': amount})

    # -----------------------
    # Volume Precision Helper
    # -----------------------
    def round_volume(self, amount, ticker):
        precision = {'XRP': 6, 'BTC': 8, 'ETH': 8, 'USDT': 2}
        decimals = precision.get(ticker.upper(), 8)
        return float(f"{amount:.{decimals}f}")

    # -----------------------
    # Place Order (Limit or Market)
    # -----------------------
    def place_order(self, ticker, action, amount, price=None, market=False):
        action = 'buy' if action == 'bid' else 'sell'
        ordertype = 'market' if market else 'limit'

        # For market buy/sell using helper functions
        if market:
            if action == 'buy':
                return buy_token_kraken(self.key['public'], self.key['private'], amount, ticker)
            else:
                return sell_token_kraken(self.key['public'], self.key['private'], amount, ticker)

        # Normalize Kraken pair
        norm = ticker.upper()
        if not (norm.startswith('X') or norm.startswith('Z')):
            if norm.endswith('USDT'):
                base, quote = norm[:-4], 'ZUSD'
                base = 'X' + base if base != 'USDT' else base
                norm = base + quote

        base_token = norm[:len(norm) - 4]
        amount = self.round_volume(amount, base_token)

        data = {
            'pair': norm,
            'type': action,
            'ordertype': ordertype,
            'volume': str(amount)
        }

        if not market:
            if price is None:
                raise ValueError("Price must be set for LIMIT orders")
            data['price'] = str(price)

        print(f"params for kraken: {data}")
        return self._send_request('private/AddOrder', 'POST', data)

    # -----------------------
    # Get Last Ticker Price
    # -----------------------
    def get_ticker_lastPrice(self, ticker):
        return self._send_request(f'public/Ticker?pair={ticker}ZUSD', 'GET', {}, [self.hook_lastPrice(ticker=ticker)])

    def hook_lastPrice(self, *factory_args, **factory_kwargs):
        def res_hook(r, *_, **__):
            json_data = r.json()
            r.parsed = {}
            r.parsed[factory_kwargs['ticker']] = float(next(iter(json_data['result'].values()))['c'][0])
        return res_hook

    # -----------------------
    # OHLC History
    # -----------------------
    def get_ticker_history(self, ticker, timeframe='1'):
        since = calendar.timegm((datetime.utcnow() - timedelta(hours=1)).timetuple())
        return self._send_request(f'public/OHLC?pair={ticker}&interval={timeframe}&since={since}', 'GET')

    def parseTickerData(self, ticker, tickerData):
        vwapIndex = 5
        for key in tickerData['result'].keys():
            if isinstance(tickerData['result'][key], list):
                return {
                    'exchange': self.key['exchange'],
                    'ticker': ticker,
                    'data': list(map(lambda x: {'price': x[vwapIndex]}, tickerData['result'][key]))
                }

    # -----------------------
    # Deposit Methods
    # -----------------------
    def get_deposit_methods(self, asset):
        params = {'asset': asset.upper()}
        r = self._send_request('private/DepositMethods', 'POST', params)
        if self.basync:
            r = grequests.map([r])[0]

        json_data = r.json()
        if json_data.get("error"):
            raise ValueError(f"Kraken API Error: {json_data['error']}")
        return json_data.get("result", [])

    # -----------------------
    # Deposit Address
    # -----------------------
    def get_deposit_address(self, asset, method=None, new=False):
        
        # if asset == "XRP":
        #     return {'address' : "rLHzPsX6oXkzU2qL12kHCH8G8cnZv1rBJh", 'tag' : "2486487676"}
        # elif asset == "USDT":
        #     return {'address' : "0x41cf1c54a9b02f70de2302dacf3b74e9dafa5333", 'tag' : "0"}
        
        asset = asset.upper()
        methods = self.get_deposit_methods(asset)
        if not methods:
            raise ValueError(f"No deposit methods available for {asset}")

        # Use the first available method if not specified
        if not method:
            method = methods[0]['method']
            print(f"Using deposit method: {method}")

        params = {'asset': asset, 'method': method, 'new': 'true' if new else 'false'}
        r = self._send_request('private/DepositAddresses', 'POST', params)
        if self.basync:
            r = grequests.map([r])[0]

        json_data = r.json()
        if json_data.get("error"):
            raise ValueError(f"Kraken API Error: {json_data['error']}")

        result = json_data.get("result", [])
        if not result:
            raise ValueError(
                f"No deposit address returned for {asset}. "
                "Try generating one manually on Kraken first."
            )

        address_info = result[0]
        return {
            'address': address_info.get('address'),
            'expiretm': address_info.get('expiretm'),
            'new': address_info.get('new', new),
            'tag': address_info.get('address-tag') or address_info.get('memo')  # for XRP/XLM/etc
        }



# -----------------------
# TEST SCRIPT
# -----------------------
if __name__ == "__main__":
    import gevent.monkey
    gevent.monkey.patch_all()

    API_PUBLIC_KEY = "F4LpC0xPGQo4DNXBQVsd48uUKE6HaRH78CapiRl8y+LuUHwehhMuJT45"
    API_PRIVATE_KEY = "RkpS3CiplIeN7Czwnv0oCMKf0WSUbOK6dE2dyqwSQowBBxrcj6lyLQcY0Z+dKrioQYdMtw21/j5FJGmHEYkwfg=="

    engine = ExchangeEngine()
    engine.key = {'public': API_PUBLIC_KEY, 'private': API_PRIVATE_KEY}

    # Try deposit address fetch (now IPv4 enforced)
    try:
        addr = engine.get_deposit_address("XRP")
        print("Deposit Address:", addr)
    except Exception as e:
        print("Failed to get deposit address:", e)
