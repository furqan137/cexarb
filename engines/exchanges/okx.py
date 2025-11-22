"""
OKX Exchange Implementation
Trading Fee: ~0.08% (maker) / 0.1% (taker)
https://www.okx.com/fees
"""

from mod_imports import *
from base import *
from urllib.parse import urlencode
import base64
import datetime
import hmac
import hashlib
import json
import grequests
import requests
import asyncio
import aiohttp
from datetime import datetime, timezone

import sys
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.insert(0, PROJECT_ROOT)

from engines.utils.check_asset_okx import okx_buy_token, okx_sell_token, okx_withdraw, okx_transfer_to_funding


class ExchangeEngine(ExchangeEngineBase):
    def __init__(self):
        self.API_URL = "https://app.okx.com"
        self.apiVersion = "v5"
        self.sleepTime = 5
        self.feeRatio = 0.004  # 0.1% trading fee
        self.basync = True
        self.key = {}

    # ------------------------
    # 🔹 Internal Helper
    # ------------------------
    def _get_timestamp(self):
        """Return ISO8601 timestamp string with milliseconds (required by OKX)."""
        r = requests.get(f"{self.API_URL}/api/v5/public/time")
        ts = int(r.json()["data"][0]["ts"]) / 1000.0
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    def _sign(self, timestamp, method, request_path, body=""):
        """Generate OKX HMAC-SHA256 signature."""
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(
            self.key["private"].encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    # ------------------------
    # 🔹 Unified Request
    # ------------------------
    def _send_request(self, command, httpMethod="GET", params=None, hook=None):
        if params is None:
            params = {}

        url = self.API_URL + command
        timestamp = self._get_timestamp()
        body = ""

        # Handle params
        if httpMethod.upper() == "GET":
            if params:
                url += "?" + urlencode(params)
        else:
            body = json.dumps(params)

        # Sign the request
        signature = self._sign(timestamp, httpMethod, command, body)

        headers = {
            "OK-ACCESS-KEY": self.key["public"],
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.key.get("passphrase", ""),
            "Content-Type": "application/json",
        }

        # Select method
        if httpMethod == "GET":
            R = grequests.get
        elif httpMethod == "POST":
            R = grequests.post
        elif httpMethod == "DELETE":
            R = grequests.delete
        else:
            raise ValueError(f"Unsupported HTTP method: {httpMethod}")

        # ✅ Proper hook attachment
        req = R(
            url,
            headers=headers,
            data=body if httpMethod != "GET" else None,
            hooks={"response": [hook]} if hook else None
        )

        # Async vs sync
        if self.basync:
            return req
        else:
            r = grequests.map([req])[0]
            return getattr(r, "parsed", r.json())

    # ------------------------
    # 🔹 Account & Balances
    # ------------------------
    def get_balance(self, tickers=[]):
        return self._send_request(
            "/api/v5/account/balance",
            "GET",
            {},
            self.hook_getBalance(tickers=tickers)
        )

    def hook_getBalance(self, *factory_args, **factory_kwargs):
        def res_hook(r, *r_args, **r_kwargs):
            json_data = r.json()
            r.parsed = {}
            if json_data.get("code") == "0" and "data" in json_data:
                balances = json_data["data"][0]["details"]
                for b in balances:
                    if not factory_kwargs["tickers"] or b["ccy"].upper() in factory_kwargs["tickers"]:
                        r.parsed[b["ccy"].upper()] = float(b["availBal"])
        return res_hook

    # ------------------------
    # 🔹 Market Data
    # ------------------------
    def get_ticker_lastPrice(self, ticker):
        symbol = f"{ticker}-USDT".upper().replace("/", "-")
        return self._send_request(
            "/api/v5/market/ticker",
            "GET",
            {"instId": symbol},
            self.hook_lastPrice(ticker=ticker)
        )

    def hook_lastPrice(self, *factory_args, **factory_kwargs):
        def res_hook(r, *r_args, **r_kwargs):
            json_data = r.json()
            r.parsed = {}
            if json_data.get("code") == "0" and "data" in json_data:
                r.parsed[factory_kwargs["ticker"]] = float(json_data["data"][0]["last"])
        return res_hook

    def get_ticker_orderBook_innermost(self, ticker):
        symbol = ticker.upper().replace("/", "-")
        return self._send_request(
            "/api/v5/market/books",
            "GET",
            {"instId": symbol, "sz": 5},
            self.hook_orderBook
        )

    def hook_orderBook(self, r, *r_args, **r_kwargs):
        json_data = r.json()
        if json_data.get("code") == "0" and "data" in json_data:
            book = json_data["data"][0]
            r.parsed = {
                "bid": {"price": float(book["bids"][0][0]), "amount": float(book["bids"][0][1])},
                "ask": {"price": float(book["asks"][0][0]), "amount": float(book["asks"][0][1])},
            }

    # ------------------------
    # 🔹 Orders
    # ------------------------
    def get_open_order(self):
        return self._send_request(
            "/api/v5/trade/orders-pending",
            "GET",
            {},
            self.hook_openOrder
        )

    def hook_openOrder(self, r, *r_args, **r_kwargs):
        json_data = r.json()
        r.parsed = []
        if json_data.get("code") == "0" and "data" in json_data:
            for order in json_data["data"]:
                r.parsed.append({
                    "orderId": str(order["ordId"]),
                    "created": order["cTime"]
                })

    async def place_order(self, ticker, action, amount, price=None, market=False, quote_order_qty=False):
        """
        Place an order asynchronously on OKX (via okx_buy_token / okx_sell_token).

        Args:
            ticker (str): Trading pair, e.g., "XLM-USDT".
            action (str): 'bid' for buy, 'ask' for sell.
            amount (float): Order amount.
            price (float, optional): Price for limit orders.
            market (bool, optional): True for market order, False for limit.
            quote_order_qty (bool, optional): Only for exchanges like Binance.

        Returns:
            dict: API response.
        """

        # ✅ Normalize symbol
        symbol = ticker.upper().replace("/", "-")

        # ✅ Log what we’re about to do
        print(f"⚙️  Placing order on OKX: {action.upper()} {symbol}, amount={amount}, "
            f"price={price}, market={market}, quote_order_qty={quote_order_qty}")

        try:
            # ✅ Choose correct async function
            if action.lower() == "bid":
                result = await okx_buy_token(symbol, amount, price=price, market=market)
            elif action.lower() == "ask":
                result = await okx_sell_token(symbol, amount, price=price, market=market)
            else:
                raise ValueError(f"Invalid action '{action}', expected 'bid' or 'ask'")

            # ✅ Check for API errors
            if not isinstance(result, dict):
                raise ValueError(f"Unexpected response type: {type(result)}")
            if result.get("code") != "0":
                print(f"❌ OKX returned an error: {result}")
            else:
                print(f"✅ OKX order successful: {result}")

            return result

        except Exception as e:
            print(f"❌ Failed to place order for {symbol}: {e}")
            return {"code": "-1", "error": str(e)}

    def cancel_order(self, orderID, ticker=""):
        params = {"ordId": orderID}
        if ticker:
            params["instId"] = ticker.upper().replace("/", "-")
        return self._send_request(
            "/api/v5/trade/cancel-order",
            "POST",
            params
        )

    # ------------------------
    # 🔹 Get Funding Balance
    # ------------------------
    def get_funding_balance(self, ccy="XLM"):
        url = f"{self.API_URL}/api/v5/asset/balances?ccy={ccy}"
        ts = self._get_timestamp()
        sign = self._sign(ts, "GET", "/api/v5/asset/balances", "")

        headers = {
            "OK-ACCESS-KEY": self.key["public"],
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.key["passphrase"],
        }

        r = requests.get(url, headers=headers)
        data = r.json()
        if data.get("code") == "0" and data["data"]:
            avail = float(data["data"][0]["availBal"])
            print(f"💰 Funding balance {ccy}: {avail}")
            return avail
        else:
            print(f"⚠️ Balance fetch failed: {data}")
            return 0.0

    # ------------------------
    # 🔹 Transfer Trading → Funding
    # ------------------------
    def transfer_to_funding(self, ccy="XLM", amt="30"):
        path = "/api/v5/asset/transfer"
        url = self.API_URL + path

        ts = self._get_timestamp()
        body_data = {
            "ccy": ccy,
            "amt": amt,
            "from": "18",  # 18 = Trading
            "to": "6",     # 6 = Funding
            "type": "0"
        }

        body = json.dumps(body_data)
        sign = self._sign(ts, "POST", path, body)

        headers = {
            "OK-ACCESS-KEY": self.key["public"],
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.key["passphrase"],
            "Content-Type": "application/json",
        }

        r = requests.post(url, headers=headers, data=body)
        print("🔁 Transfer response:", r.json())
        return r.json()

    # ------------------------
    # 🔹 Withdraw (Auto-Transfer + Withdraw)
    # ------------------------
    def withdraw(self, coin, amount, address, network=None, memo=None):
        
        okx_transfer_to_funding(coin, amount)
        print("-----------------------")
        return okx_withdraw(coin, amount, address, network, memo)
        
        coin = coin.upper()

        # 🟡 XLM/XRP/EOS require tag
        if coin in ["XLM", "XRP", "EOS"] and not memo:
            raise ValueError(f"{coin} withdrawal requires a memo/tag.")

        # 🟢 Format address correctly for tag-based coins
        if coin in ["XLM", "XRP", "EOS"]:
            to_address = f"{address}:{memo}"
            chain = None
        else:
            to_address = address
            chain = network

        # ✅ Round amount
        amount = round(amount, 7 if coin in ["XLM", "XRP"] else 4)

        # ✅ Ensure funds are in funding account
        avail = self.get_funding_balance(coin)
        if avail < amount:
            diff = round(amount - avail + 1, 4)
            print(f"⚙️ Not enough in funding ({avail}). Transferring {diff} {coin} from trading...")
            self.transfer_to_funding(coin, str(diff))
            time.sleep(2)  # Wait for transfer to settle

        # ✅ Withdraw request
        path = "/api/v5/asset/withdrawal"
        ts = self._get_timestamp()

        body_data = {
            "ccy": coin,
            "amt": str(amount),
            "dest": "4",
            "toAddr": to_address
        }

        if chain and coin not in ["XLM", "XRP", "EOS"]:
            body_data["chain"] = chain

        body = json.dumps(body_data)
        sign = self._sign(ts, "POST", path, body)

        headers = {
            "OK-ACCESS-KEY": self.key["public"],
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.key["passphrase"],
            "Content-Type": "application/json",
        }

        print("➡️ Payload:", body_data)
        r = requests.post(self.API_URL + path, headers=headers, data=body)
        data = r.json()
        print("🔁 Response:", data)

        if data.get("code") == "0":
            print(f"✅ Withdrawal successful: {amount} {coin}")
        else:
            print(f"❌ Withdrawal failed: {data}")

        return data

    def get_deposit_address(self, coin: str):
        """
        Get deposit address for a given token on OKX.
        Example: okx_get_deposit_address("XLM")
        Returns {'address': '...', 'tag': '...'} if available.
        """
        try:
            path = f"/api/v5/asset/deposit-address?ccy={coin.upper()}"
            url = self.API_URL + path

            ts = self._get_timestamp()
            body = ""
            sign = self._sign(ts, "GET", path, body)

            headers = {
                "OK-ACCESS-KEY": self.key["public"],
                "OK-ACCESS-SIGN": sign,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self.key.get("passphrase", ""),
                "Content-Type": "application/json",
                "x-simulated-trading": "1" if False else "0",
            }

            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()

            # Validate response
            if data.get("code") != "0":
                raise ValueError(f"Failed to get deposit address for {coin}: {data}")

            address_data = data["data"][0] if data.get("data") else {}
            address = address_data.get("addr")
            tag = address_data.get("tag") or address_data.get("memo")

            return {"address": address, "tag": tag}

        except Exception as e:
            print(f"❌ Error fetching OKX deposit address for {coin}: {e}")
            return {"address": None, "tag": None}   


# ------------------------
# ✅ Example Usage
# ------------------------
if __name__ == "__main__":
    engine = ExchangeEngine()
    engine.load_instance("keys/okx.key")

    # ✅ Async example
    # engine.basync = True
    # reqs = [
    #     engine.get_balance(["BTC", "USDT"]),
    #     engine.get_ticker_lastPrice("BTC-USDT"),
    # ]
    # results = grequests.map(reqs)
    # for r in results:
    #     print("status:", getattr(r, "status_code", None), "parsed:", getattr(r, "parsed", None))

    # # ✅ Sync example
    # engine.basync = False
    # balance = engine.get_balance(["BTC", "USDT"])
    # last = engine.get_ticker_lastPrice("BTC-USDT")
    # print("sync balance:", balance)
    # print("sync last:", last)
    engine.withdraw("XLM", 21.1, "GC7ANIOVX27Z6CL3U2PSVWDCJUEEEUKNIYSFGU2BXPROE3L7Q5GNI7CN", "XLM-Stellar Lumens", "2465307129")
