import time
import hmac
import hashlib
import base64
import requests
import urllib.parse
import json


import socket
import requests.packages.urllib3.util.connection as urllib3_cn

# ==========================
# 🔹 UNIVERSAL UTILS
# ==========================

def allowed_gai_family():
    # Force IPv4
    return socket.AF_INET

urllib3_cn.allowed_gai_family = allowed_gai_family

# ------------------------------
# Crypto.com API config
# ------------------------------
with open('keys/crypto.key') as f:
    crypto_key = json.load(f)

CRYPTO_KEY_PUBLIC = crypto_key['public']
CRYPTO_KEY_PRIVATE = crypto_key['private']
# CRYPTO_BASE = "https://api.crypto.com/exchange/v1"
CRYPTO_BASE = "https://api.crypto.com/v2"


# =====================================================================
# CRYPTO.COM
# =====================================================================
CRYPTO_BASE = "https://api.crypto.com/v2"
def crypto_sign_exchange(req):
    """Signature for Crypto.com Exchange API"""
    param_str = ""
    for key in sorted(req["params"]):
        param_str += key + str(req["params"][key])
    payload = req["method"] + str(req["id"]) + CRYPTO_KEY_PUBLIC + param_str + str(req["nonce"])
    sig = hmac.new(
        CRYPTO_KEY_PRIVATE.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest().upper()  # must be UPPERCASE
    return sig

def crypto_get_balances_exchange():
    url = f"https://api.crypto.com/v2/private/get-account-summary"
    now = int(time.time() * 1000)

    req = {
        "id": now,
        "method": "private/get-account-summary",
        "api_key": CRYPTO_KEY_PUBLIC,
        "params": {},
        "nonce": now
    }
    req["sig"] = crypto_sign_exchange(req)

    print(f"req : {req}")

    headers = {"Content-Type": "application/json"}
    r = requests.post(url, data=json.dumps(req), headers=headers)
    # print("Payload:", json.dumps(req, indent=2))
    # print("Response:", json.dumps(r.json(), indent=2))
    return r.json()

def crypto_get_order():
    url = f"{CRYPTO_BASE}/private/get-open-orders"
    now = int(time.time() * 1000)

    req = {
        "id": now,
        "method": "private/get-open-orders",
        "api_key": CRYPTO_KEY_PUBLIC,
        "params": {},
        "nonce": now
    }
    req["sig"] = crypto_sign_exchange(req)
    
    print(f"req : {req}")

    headers = {"Content-Type": "application/json"}
    r = requests.post(url, data=json.dumps(req), headers=headers)
    # print("Payload:", json.dumps(req, indent=2))
    # print("Response:", json.dumps(r.json(), indent=2))
    return r.json()

def crypto_get_token_price(token: str):
    """
    Get the current price for a token pair from Crypto.com.
    Example symbol: 'BTC_USDT', 'XLM_USDT', 'ETH_USDT'
    """

    symbol = f"{token}_USDT"
    url = f"{CRYPTO_BASE}/public/get-ticker"
    params = {"instrument_name": symbol}

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
 
        if "result" in data and "data" in data["result"] and len(data["result"]["data"]) > 0:
            ticker = data["result"]["data"][0]
            price = float(ticker.get("a") or ticker.get("c") or 0.0)
            # print(f"[Crypto.com] {symbol} → {price:.6f} USDT")
            return price
        else:
            print(f"⚠️ No price data for {symbol}")
            return 0.0

    except Exception as e:
        print(f"❌ Error fetching {symbol} price: {e}")
        return 0.0

def crypto_sign_exchange_v2(req):
    """Signature for Crypto.com Exchange v2 API (exchange endpoints)"""
    payload = json.dumps(req["params"], separators=(",", ":"))  # no spaces
    message = req["api_key"] + str(req["nonce"]) + payload

    sig = hmac.new(
        CRYPTO_KEY_PRIVATE.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest().upper()
    return sig


def crypto_sell_token(ticker: str, quantity: float):
    url = "https://api.crypto.com/exchange/v2/private/create-order"
    now = int(time.time() * 1000)

    # Convert numbers to strings
    params = {
        "instrument_name": ticker,      # e.g., "XLM_USDT"
        "side": "SELL",                 # must be uppercase
        "type": "MARKET",               # must be uppercase
        "quantity": f"{quantity:.8f}"   # must be string
    }

    req = {
        "id": now,
        "api_key": CRYPTO_KEY_PUBLIC,
        "nonce": now,
        "params": params
    }

    # Signature: sign JSON with no spaces
    payload_json = json.dumps(params, separators=(",", ":"))
    message = req["api_key"] + str(req["nonce"]) + payload_json
    sig = hmac.new(
        CRYPTO_KEY_PRIVATE.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest().upper()
    req["sig"] = sig

    headers = {"Content-Type": "application/json"}
    
    print(f"req : {req}")
    
    response = requests.post(url, data=json.dumps(req), headers=headers)
    print(response.text)
    return response.json()


def crypto_total_usdt():
    print("----------Total asset in Crypto----------")
    balances_resp = crypto_get_balances_exchange()

    accounts = balances_resp.get("result", {}).get("accounts", [])
    if not accounts:
        print("⚠️ No balances found")
        return 0.0, []

    # ✅ public endpoints still use GET
    prices = requests.get(f"{CRYPTO_BASE}/public/get-ticker").json()
    tickers = {
        t["i"]: float(t["a"])
        for t in prices.get("result", {}).get("data", [])
        if "a" in t
    }

    total = 0.0
    details = []
    for b in accounts:
        coin = b["currency"]
        amount = float(b["available"])
        if amount <= 0:
            continue
        pair = f"{coin}_USDT"
        value = amount * tickers.get(pair, 1)
        details.append({"asset": coin, "amount": amount, "value_usdt": value})
        print(f"[Crypto.com] {coin}: {amount} → {value:.2f} USDT")
        total += value       

    return total, details

if __name__ == "__main__":

    crypto_price = crypto_get_token_price("XLM")
    print(f"crypto_price : {crypto_price}")
