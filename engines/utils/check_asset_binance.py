import time
import hmac
import hashlib
import base64
import requests
import urllib.parse
import json
import aiohttp
import asyncio
import math

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
# Binance API config
# ------------------------------
with open('keys/binance.key') as f:
    binance_key = json.load(f)

BINANCE_API_KEY = binance_key['public']
BINANCE_API_SECRET = binance_key['private']
BINANCE_BASE = "https://api.binance.us"

# =====================================================================
# BINANCE
# =====================================================================
def binance_sign(params: dict):
    query = urllib.parse.urlencode(params)
    signature = hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    return query + "&signature=" + signature

def binance_get_account_info():
    ts = int(time.time() * 1000)
    params = {"timestamp": ts, "recvWindow": 60000}
    qs = binance_sign(params)
    url = f"{BINANCE_BASE}/api/v3/account?{qs}"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()

def binance_get_all_prices():
    url = f"{BINANCE_BASE}/api/v3/ticker/price"
    r = requests.get(url)
    r.raise_for_status()
    return {item["symbol"]: float(item["price"]) for item in r.json()}

def binance_get_price(symbol: str) -> float:
    """
    Fetch the latest price for a given trading pair from Binance.US.
    Example:
        binance_get_price("XLMUSDT") -> 0.27236
    """
    url = f"{BINANCE_BASE}/api/v3/ticker/price?symbol={symbol.upper()}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return float(data["price"])
    except Exception as e:
        print(f"❌ Error fetching price for {symbol}: {e}")
        return 0.0

def binance_asset_to_usdt(asset, amount, prices):
    asset = asset.upper()
    if amount == 0:
        return 0.0
    if asset in ("USDT", "BUSD", "USDC", "DAI", "TUSD"):
        return amount
    if asset + "USDT" in prices:
        return amount * prices[asset + "USDT"]
    if "USDT" + asset in prices and prices["USDT" + asset] != 0:
        return amount / prices["USDT" + asset]
    if asset == "XRP" and "XRPUSDT" in prices:
        return amount * prices["XRPUSDT"]
    if asset == "XLM" and "XLMUSDT" in prices:
        return amount * prices["XLMUSDT"]
    if asset + "BTC" in prices and "BTCUSDT" in prices:
        return amount * prices[asset + "BTC"] * prices["BTCUSDT"]
    if asset + "ETH" in prices and "ETHUSDT" in prices:
        return amount * prices[asset + "ETH"] * prices["ETHUSDT"]
    return 0.0

def binance_total_usdt():
    print("----------Total asset in Binance----------")
    acct = binance_get_account_info()
    balances = acct.get("balances", [])
    prices = binance_get_all_prices()
    total = 0.0
    details = []
    for entry in balances:
        asset = entry["asset"]
        amount = float(entry.get("free", 0.0)) + float(entry.get("locked", 0.0))
        if amount <= 0 or asset not in ["USDT"]:
            continue
        value_usdt = binance_asset_to_usdt(asset, amount, prices)
        details.append({"asset": asset, "amount": amount, "value_usdt": value_usdt})
        print(f"[Binance] {asset}: {amount} → {value_usdt:.2f} USDT")
        
        total += value_usdt
    return total, details

def get_lot_size(symbol="XLMUSDT"):
    """Fetch lot size filter info for a given symbol (non-async version)."""
    url = f"https://api.binance.us/api/v3/exchangeInfo?symbol={symbol}"
    resp = requests.get(url)
    data = resp.json()
    filters = data["symbols"][0]["filters"]
    lot = next(f for f in filters if f["filterType"] == "LOT_SIZE")
    return {
        "minQty": float(lot["minQty"]),
        "maxQty": float(lot["maxQty"]),
        "stepSize": float(lot["stepSize"]),
    }

def round_step_size(quantity, step_size):
    """Round quantity down to the nearest multiple of step_size."""
    return math.floor(quantity / step_size) * step_size


# ----------------------------
# 🟢 Market Buy
# ----------------------------

async def binance_buy_token(api_key, api_secret, amount_quote, token_pair="XLMUSDT"):
    """
    Buy token (base asset) with quote asset on Binance (USDT pair).
    Uses quoteOrderQty to spend a fixed amount of USDT.
    """
    print(f"xxxxxxxx-buy-{token_pair}-binance-xxxxxxxx")

    base_url = "https://api.binance.us"
    endpoint = "/api/v3/order"
    side = "BUY"
    order_type = "MARKET"
    timestamp = int(time.time() * 1000)

    # Market buy uses quoteOrderQty (amount in USDT)
    params = f"symbol={token_pair}&side={side}&type={order_type}&quoteOrderQty={amount_quote:.4f}&timestamp={timestamp}"
    signature = hmac.new(api_secret.encode(), params.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{params}&signature={signature}"

    headers = {"X-MBX-APIKEY": api_key}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers) as resp:
            response = await resp.json()
            print("Buy response:", response)
            return response


# ----------------------------
# 🔴 Market Sell
# ----------------------------

async def binance_sell_token(api_key, api_secret, amount_base, token_pair="XLMUSDT"):
    """
    Sell token (base asset) for quote asset on Binance.
    Automatically rounds to correct step size based on LOT_SIZE.
    """
    print(f"xxxxxxxx-sell-{token_pair}-binance-xxxxxxxx")

    lot = get_lot_size(token_pair)
    step_size = lot["stepSize"]
    min_qty = lot["minQty"]
    max_qty = lot["maxQty"]

    # Round quantity to match Binance step size
    qty = round_step_size(amount_base, step_size)

    if qty < min_qty:
        raise ValueError(f"❌ Quantity {qty} below minQty {min_qty} for {token_pair}")
    if qty > max_qty:
        raise ValueError(f"❌ Quantity {qty} above maxQty {max_qty} for {token_pair}")

    base_url = "https://api.binance.us"
    endpoint = "/api/v3/order"
    side = "SELL"
    order_type = "MARKET"
    timestamp = int(time.time() * 1000)

    params = f"symbol={token_pair}&side={side}&type={order_type}&quantity={qty}&timestamp={timestamp}"
    signature = hmac.new(api_secret.encode(), params.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{params}&signature={signature}"

    headers = {"X-MBX-APIKEY": api_key}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers) as resp:
            response = await resp.json()
            print("Sell response:", response)
            return response
        
def binance_withdraw(api_key, api_secret, asset, address, amount, network=None, memo=None):
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
    base_url = "https://api.binance.us"
    endpoint = "/sapi/v1/capital/withdraw/apply"
    timestamp = int(time.time() * 1000)

    params = {
        "coin": asset.upper(),
        "address": address,
        "amount": f"{amount:.4f}",
        "timestamp": timestamp,
    }
    if network:
        params["network"] = network
    if memo:
        params["addressTag"] = memo
        
    print(f"Withdraw info : {params}")

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

def binance_get_deposit_address(api_key, api_secret, asset="USDT", network=None):
    """
    Fetch deposit address for a given asset (and optional network) from Binance.US.

    Args:
        api_key (str): Binance API key
        api_secret (str): Binance API secret
        asset (str): Token symbol, e.g., 'USDT', 'BTC', 'ETH'
        network (str): Optional network name, e.g., 'BSC', 'ETH', 'TRX'

    Returns:
        dict: Deposit address info (includes address and tag/memo if applicable)
    """
    base_url = "https://api.binance.us"
    endpoint = "/sapi/v1/capital/deposit/address"
    timestamp = int(time.time() * 1000)

    params = {"coin": asset.upper(), "timestamp": timestamp}
    if network:
        params["network"] = network.upper()

    query_string = urllib.parse.urlencode(params)
    signature = hmac.new(api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{query_string}&signature={signature}"

    headers = {"X-MBX-APIKEY": api_key}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()

        print(f"✅ Deposit address for {asset} ({network or 'default'}): {data}")
        return data
    except Exception as e:
        print(f"❌ Error fetching deposit address for {asset}: {e} → {r.text if 'r' in locals() else ''}")
        return {"error": str(e)}


if __name__ == "__main__":
    # res = binance_get_all_prices()
    
    # for key in res:
    #     if key == "XLMUSDT":
    #         price = res.get("XLMUSDT", 0)
    #         print(f"binance_price : {price}" )

    asyncio.run(binance_sell_token(BINANCE_API_KEY, BINANCE_API_SECRET, 12.8226, "XRPUSDT"))

    # Example for TRON network (most common for USDT)
    # res = binance_get_deposit_address(
    #     BINANCE_API_KEY,
    #     BINANCE_API_SECRET,
    #     asset="AVAX",
    #     network="AVAXC"   # or "BSC" / "ETH"
    # )
    # print("AVAX Deposit Address:", res)

    # res = binance_withdraw(
    #     BINANCE_API_KEY,
    #     BINANCE_API_SECRET,
    #     asset="USDT",
    #     address="0x610a094272b3c701be66de82384413fa7f153457",  # Replace with valid KuCoin deposit address
    #     amount=10,
    #     network="ETH",  # TRON network
    #     memo=None
    # )
    # print(res)
    
            