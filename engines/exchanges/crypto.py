"""
Crypto.com Exchange Implementation
Trading Fee: ~0.04% (maker) / 0.04% (taker)
Docs: https://crypto.com/exchange/documentation/api/v2
"""

from mod_imports import *
from base import *
import time
import hmac
import hashlib
import json
import grequests
from urllib.parse import urlencode


class ExchangeEngine(ExchangeEngineBase):
    def __init__(self):
        self.API_URL = "https://api.crypto.com/v2"
        self.sleepTime = 5
        self.feeRatio = 0.0004  # 0.04%
        self.basync = True
        self.key = {}

    # ------------------------------------------------------------
    # 🔹 Signing / Helper
    # ------------------------------------------------------------
    def _get_nonce(self):
        return int(time.time() * 1000)

    def _sign(self, req):
        """Crypto.com v2 signature: sig = HMAC_SHA256(api_secret, payload).upper()"""
        param_str = ""
        for k in sorted(req["params"]):
            param_str += k + str(req["params"][k])

        payload = req["method"] + str(req["id"]) + self.key["public"] + param_str + str(req["nonce"])
        sig = hmac.new(
            self.key["private"].encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest().upper()
        return sig

    # ------------------------------------------------------------
    # 🔹 Unified Request Handler
    # ------------------------------------------------------------
    def _send_request(self, command, httpMethod="GET", params=None, hook=None):
        """
        Unified request handler for Crypto.com API v2.
        Handles both public and private endpoints automatically.
        """
        if params is None:
            params = {}

        url = self.API_URL + command
        headers = {}
        args = {}

        # Detect if private endpoint
        is_private = command.startswith("/private/") or command.startswith("private/")

        if is_private:
            # Private signed request
            now = self._get_nonce()
            req_body = {
                "id": now,
                "method": command.lstrip("/"),  # e.g. "private/get-account-summary"
                "api_key": self.key["public"],
                "params": params,
                "nonce": now
            }
            req_body["sig"] = self._sign(req_body)
            headers = {"Content-Type": "application/json"}
            args["json"] = req_body
            httpMethod = "POST"  # Crypto.com private endpoints are always POST
        else:
            # Public GET request
            if params:
                args["params"] = params
            httpMethod = "GET"

        # Choose request method
        if httpMethod == "POST":
            R = grequests.post
        elif httpMethod == "DELETE":
            R = grequests.delete
        else:
            R = grequests.get

        # Attach hooks properly
        if hook:
            args["hooks"] = {"response": [hook]}

        args["headers"] = headers
        req_obj = R(url, **args)

        if self.basync:
            return req_obj
        else:
            r = grequests.map([req_obj])[0]
            return getattr(r, "parsed", r.json())

    # ------------------------------------------------------------
    # 🔹 Account / Balances
    # ------------------------------------------------------------
    def get_balance(self, tickers=[]):
        return self._send_request(
            "/private/get-account-summary",
            "POST",
            {},
            self.hook_getBalance(tickers=tickers)
        )

    def hook_getBalance(self, *args, **kwargs):
        def res_hook(r, *r_args, **r_kwargs):
            json_data = r.json()
            r.parsed = {}
            if json_data.get("code") == 0 and "result" in json_data:
                for acc in json_data["result"].get("accounts", []):
                    ccy = acc["currency"].upper()
                    if not kwargs.get("tickers") or ccy in kwargs.get("tickers"):
                        r.parsed[ccy] = float(acc["available"])
        return res_hook

    # ------------------------------------------------------------
    # 🔹 Market Data
    # ------------------------------------------------------------
    def get_ticker_lastPrice(self, ticker):
        symbol = f"{ticker}_USDT".upper().replace("/", "_")
        return self._send_request(
            "/public/get-ticker",
            "GET",
            {"instrument_name": symbol},
            self.hook_lastPrice(ticker=ticker)
        )

    def hook_lastPrice(self, *args, **kwargs):
        def res_hook(r, *r_args, **r_kwargs):
            ticker = kwargs.get("ticker")
            json_data = r.json()
            r.parsed = {}
            if "result" in json_data and "data" in json_data["result"]:
                data = json_data["result"]["data"]
                if isinstance(data, list) and len(data) > 0:
                    price = data[0].get("a") or data[0].get("last") or data[0].get("price")
                    if price:
                        r.parsed[ticker] = float(price)
        return res_hook

    # ------------------------------------------------------------
    # 🔹 Orders
    # ------------------------------------------------------------
    def place_order(self, ticker, action, amount, price=None, market=False):
        side = "BUY" if action == "bid" else "SELL"
        params = {
            "instrument_name": ticker.upper(),
            "side": side,
            "type": "MARKET" if market else "LIMIT",
            "quantity": str(amount)
        }
        if not market and price:
            params["price"] = str(price)

        return self._send_request(
            "/private/create-order",
            "POST",
            params,
            self.hook_placeOrder()
        )

    def hook_placeOrder(self):
        def res_hook(r, *r_args, **r_kwargs):
            json_data = r.json()
            r.parsed = json_data.get("result", {}) if "result" in json_data else json_data
        return res_hook

    def cancel_order(self, orderID, ticker=None):
        params = {"order_id": str(orderID)}
        if ticker:
            params["instrument_name"] = ticker.upper()
        return self._send_request(
            "/private/cancel-order",
            "POST",
            params,
            self.hook_cancelOrder()
        )

    def hook_cancelOrder(self):
        def res_hook(r, *r_args, **r_kwargs):
            json_data = r.json()
            r.parsed = json_data.get("result", {}) if "result" in json_data else json_data
        return res_hook

    def get_open_order(self, ticker=None):
        params = {"instrument_name": ticker.upper()} if ticker else {}
        return self._send_request(
            "/private/get-open-orders",
            "POST",
            params,
            self.hook_openOrder
        )

    def hook_openOrder(self, r, *r_args, **r_kwargs):
        json_data = r.json()
        r.parsed = []
        if json_data.get("code") == 0 and "result" in json_data:
            for o in json_data["result"].get("order_list", []):
                r.parsed.append({
                    "orderId": str(o["order_id"]),
                    "created": o["create_time"]
                })

    # ------------------------------------------------------------
    # 🔹 Withdraw
    # ------------------------------------------------------------
    def withdraw(self, coin, amount, address, network=None):
        params = {
            "currency": coin.upper(),
            "amount": str(amount),
            "address": address
        }
        if network:
            params["chain"] = network.upper()

        return self._send_request(
            "/private/crypto/withdraw",
            "POST",
            params,
            self.hook_withdraw()
        )

    def hook_withdraw(self):
        def res_hook(r, *r_args, **r_kwargs):
            json_data = r.json()
            r.parsed = json_data.get("result", {}) if "result" in json_data else json_data
        return res_hook

    # ------------------------------------------------------------
    # 🔹 Load Keys
    # ------------------------------------------------------------
    def load_instance(self, path):
        with open(path) as f:
            self.key = json.load(f)


# ------------------------------------------------------------
# ✅ Example Usage
# ------------------------------------------------------------
if __name__ == "__main__":
    engine = ExchangeEngine()
    engine.load_instance("keys/crypto.key")

    # ✅ Async example
    engine.basync = True
    reqs = [
        engine.get_balance(["BTC", "USDT"]),
        engine.get_ticker_lastPrice("BTC_USDT")
    ]
    results = grequests.map(reqs)
    for r in results:
        print("status:", getattr(r, "status_code", None), "parsed:", getattr(r, "parsed", None))

    # ✅ Sync example
    engine.basync = False
    balance = engine.get_balance(["BTC", "USDT"])
    last = engine.get_ticker_lastPrice("BTC_USDT")
    print("sync balance:", balance)
    print("sync last:", last)
