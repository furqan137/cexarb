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
# Kraken API config
# ------------------------------
with open('keys/kraken.key') as f:
    kraken_key = json.load(f)

KRAKEN_KEY_PUBLIC = kraken_key['public']
KRAKEN_KEY_PRIVATE = kraken_key['private']

# ------------------------------
# Kraken asset mapping
# ------------------------------
KRAKEN_ASSET_MAP = {
    "USDT": "USDT",
    "USD": "ZUSD",
    "BTC": "XXBT",
    "ETH": "XETH",
    "XRP": "XXRP",
    "LTC": "XLTC",
    "BCH": "BCH",
    "XLM": "XXLM",
}

# =====================================================================
# KRAKEN
# =====================================================================
def kraken_get_balances():
    path = "/0/private/Balance"
    url = "https://api.kraken.com" + path
    nonce = int(time.time() * 1000)
    params = {"nonce": nonce}
    postdata = urllib.parse.urlencode(params)
    message = path.encode() + hashlib.sha256((str(nonce) + postdata).encode()).digest()
    signature = hmac.new(base64.b64decode(KRAKEN_KEY_PRIVATE), message, hashlib.sha512)
    api_sign = base64.b64encode(signature.digest()).decode()
    headers = {"API-Key": KRAKEN_KEY_PUBLIC, "API-Sign": api_sign}
    r = requests.post(url, data=postdata, headers=headers)
    data = r.json()
    if data.get("error"):
        print("Kraken API Error:", data["error"])
        return {}
    return data.get("result", {})

def kraken_get_ticker(pair):
    url = "https://api.kraken.com/0/public/Ticker"
    r = requests.get(url, params={"pair": pair})
    data = r.json()
    if data.get("error"):
        return 0.0
    try:
        return float(list(data["result"].values())[0]["c"][0])
    except Exception:
        return 0.0

def kraken_convert_to_usdt(asset, amount):
    asset = asset.upper()
    if amount <= 0:
        return 0.0
    mapped = KRAKEN_ASSET_MAP.get(asset, asset)
    pair = mapped + "ZUSD"
    price = kraken_get_ticker(pair)
    return amount * price if price else amount

def kraken_total_usdt():
    print("----------Total asset in Kraken----------")
    balances = kraken_get_balances()
    total = 0.0
    details = []
    for asset, amount in balances.items():
        a = float(amount)
        if a <= 0:
            continue
        value_usdt = kraken_convert_to_usdt(asset, a)
        details.append({"asset": asset, "amount": a, "value_usdt": value_usdt})
        print(f"[Kraken] {asset}: {a} → {value_usdt:.2f} USDT")
        total += value_usdt
    return total, details


if __name__ == "__main__":
    #print("kraken")
    price=kraken_get_ticker("XXLMZUSD")
    print(f"Price : {price}")
    # res = crypto_get_balances_exchange()
    # print(f"responde : {res}")
    # res = crypto_sell_token_limit("XLM_USDT", 51.0)
    #print(f"Sell result : {res}")