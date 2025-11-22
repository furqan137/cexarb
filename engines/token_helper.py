import time
import hmac
import hashlib
import base64
import requests
import urllib.parse
import aiohttp
import asyncio
import json

# ===========================================
# Force Python HTTP connections to use IPv4
# ===========================================
import socket
import urllib3.util.connection as urllib3_cn

def allowed_gai_family():
    return socket.AF_INET  # Force IPv4

urllib3_cn.allowed_gai_family = allowed_gai_family


def get_nonce():
    """Generate strictly increasing nonce for Kraken private requests."""
    return str(int(time.time() * 1000))

def sign_kraken(api_secret, url_path, data):
    """Create Kraken API signature."""
    postdata = urllib.parse.urlencode(data)
    encoded = (data["nonce"] + postdata).encode()
    message = url_path.encode() + hashlib.sha256(encoded).digest()
    signature = hmac.new(base64.b64decode(api_secret), message, hashlib.sha512)
    return base64.b64encode(signature.digest()).decode(), postdata

# ==========================
# 🔹 KRAKEN TRADING
# ==========================
async def buy_token_kraken(api_key, api_secret, amount_quote, token_pair="ETHUSDT"):
    """
    Buy a token (base asset) with a quote currency (e.g., buy ETH with USDT) on Kraken.
    """
    print(f"xxxxxxxx-buy-{token_pair}-kraken-xxxxxxxx")

    pair = token_pair
    ticker_url = f"https://api.kraken.com/0/public/Ticker?pair={pair}"
    async with aiohttp.ClientSession() as session:
        async with session.get(ticker_url) as price_resp:
            price_data = await price_resp.json()

    if price_data.get("error"):
        print("Ticker error:", price_data["error"])
        return price_data

    price = float(next(iter(price_data["result"].values()))["c"][0])
    volume = amount_quote / price
    print(f"Price: {price}, Volume to buy: {volume:.6f}")

    url_path = "/0/private/AddOrder"
    url = f"https://api.kraken.com{url_path}"

    data = {
        "nonce": get_nonce(),
        "pair": pair,
        "type": "buy",
        "ordertype": "market",
        "volume": str(round(volume, 6))
    }

    api_sign, postdata = sign_kraken(api_secret, url_path, data)

    headers = {
        "API-Key": api_key,
        "API-Sign": api_sign,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=postdata, headers=headers) as resp:
            response = await resp.json()
            print("Buy response:", response)
            return response

async def sell_token_kraken(api_key, api_secret, amount_base, token_pair="ETHUSDT"):
    """
    Sell a token (base asset) for a quote currency (e.g., sell ETH for USDT) on Kraken.
    """
    print(f"xxxxxxxx-sell-{token_pair}-kraken-xxxxxxxx")

    url_path = "/0/private/AddOrder"
    url = f"https://api.kraken.com{url_path}"

    data = {
        "nonce": get_nonce(),
        "pair": token_pair,
        "type": "sell",
        "ordertype": "market",
        "volume": str(round(amount_base, 6))
    }

    api_sign, postdata = sign_kraken(api_secret, url_path, data)

    headers = {
        "API-Key": api_key,
        "API-Sign": api_sign,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=postdata, headers=headers) as resp:
            response = await resp.json()
            print("Sell response:", response)
            return response

async def withdraw_kraken(api_key, api_secret, asset, amount, withdraw_key):
    """
    Asynchronously withdraw any asset from Kraken using a preconfigured withdrawal key.

    Parameters:
        api_key (str): Kraken API key
        api_secret (str): Kraken API private key (base64 encoded)
        asset (str): Token symbol, e.g. "XRP", "BTC", "ETH", "USDT"
        amount (float): Amount to withdraw
        withdraw_key (str): Label of the withdrawal key configured in Kraken UI

    Notes:
        - The withdrawal key must be configured in your Kraken account beforehand.
        - Asset symbol must match Kraken's format (e.g., "XXBT", "XETH", "XXRP", "USDT", "ZUSD").
        - Kraken will handle network selection based on the key’s configuration.
    """

    print(f"xxxxxxxx-withdraw-{asset.lower()}-kraken-async-xxxxxxxx")

    url_path = "/0/private/Withdraw"
    url = f"https://api.kraken.com{url_path}"
    nonce = str(int(time.time() * 1000))

    # Build post data
    data = {
        "nonce": nonce,
        "asset": asset,
        "key": withdraw_key,
        "amount": str(round(amount, 8)),  # Kraken supports up to 8 decimal precision
    }

    postdata = urllib.parse.urlencode(data)
    encoded = (nonce + postdata).encode()
    message = url_path.encode() + hashlib.sha256(encoded).digest()

    # Sign request
    signature = hmac.new(
        base64.b64decode(api_secret),
        message,
        hashlib.sha512
    )
    api_sign = base64.b64encode(signature.digest())

    headers = {
        "API-Key": api_key,
        "API-Sign": api_sign.decode()
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=postdata, headers=headers) as resp:
            resp_json = await resp.json()
            print("Withdraw response:", resp_json)
            return resp_json
        
def buy_usdt_kraken(api_key, api_secret, amount_usd):
    """
    Buy USDT with USD on Kraken (market order).
    
    amount_usd: how much USD you want to spend
    """
    pair = "USDTUSD"
    url = "https://api.kraken.com/0/private/AddOrder"
    nonce = str(int(time.time() * 1000))

    # 1) Get current USDTUSD price
    ticker_url = f"https://api.kraken.com/0/public/Ticker?pair={pair}"
    price_resp = requests.get(ticker_url).json()
    price = float(next(iter(price_resp['result'].values()))['c'][0])

    # 2) Compute volume in USDT
    volume = amount_usd / price

    # 3) Prepare order data
    data = {
        "nonce": nonce,
        "pair": pair,
        "type": "buy",           # BUY USDT with USD
        "ordertype": "market",
        "volume": str(round(volume, 6))  # Kraken supports up to 6 decimals for USDT
    }

    postdata = urllib.parse.urlencode(data)
    message = (nonce + postdata).encode()
    sha256_hash = hashlib.sha256(message).digest()
    signature = hmac.new(
        base64.b64decode(api_secret),
        b"/0/private/AddOrder" + sha256_hash,
        hashlib.sha512
    )
    api_sign = base64.b64encode(signature.digest())

    headers = {
        "API-Key": api_key,
        "API-Sign": api_sign
    }

    resp = requests.post(url, data=postdata, headers=headers)
    return resp.json()


# ==========================
# 🔹 BINANCE TRADING
# ==========================
async def buy_token_binance(api_key, api_secret, amount_quote, token_pair="ETHUSDT"):
    """Buy token (base asset) with quote asset on Binance."""
    print(f"xxxxxxxx-buy-{token_pair}-binance-xxxxxxxx")

    base_url = "https://api.binance.us"
    endpoint = "/api/v3/order"
    side = "BUY"
    order_type = "MARKET"
    timestamp = int(time.time() * 1000)

    params = f"symbol={token_pair}&side={side}&type={order_type}&quoteOrderQty={amount_quote:.4f}&timestamp={timestamp}"
    signature = hmac.new(api_secret.encode(), params.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{params}&signature={signature}"

    headers = {"X-MBX-APIKEY": api_key}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers) as resp:
            response = await resp.json()
            print("Buy response:", response)
            return response


async def sell_token_binance(api_key, api_secret, amount_base, token_pair="ETHUSDT"):
    """Sell token (base asset) for quote asset on Binance."""
    print(f"xxxxxxxx-sell-{token_pair}-binance-xxxxxxxx")

    base_url = "https://api.binance.us"
    endpoint = "/api/v3/order"
    side = "SELL"
    order_type = "MARKET"
    timestamp = int(time.time() * 1000)

    params = f"symbol={token_pair}&side={side}&type={order_type}&quantity={amount_base:.6f}&timestamp={timestamp}"
    signature = hmac.new(api_secret.encode(), params.encode(), hashlib.sha256).hexdigest()
    url = f"{base_url}{endpoint}?{params}&signature={signature}"

    headers = {"X-MBX-APIKEY": api_key}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers) as resp:
            response = await resp.json()
            print("Sell response:", response)
            return response

async def withdraw_binance(api_key, api_secret, coin, amount, address, network=None, address_tag=None):
    """
    Asynchronously withdraw any crypto asset from Binance (forces IPv4).
    
    Parameters:
        api_key (str): Binance API key
        api_secret (str): Binance API secret
        coin (str): Token symbol, e.g. "XRP", "BTC", "USDT"
        amount (float): Amount of token to withdraw
        address (str): Destination wallet address
        network (str): (Optional) Network name, e.g. "XRP", "ETH", "BSC", "TRX"
        address_tag (str): (Optional) Destination tag or memo (for XRP, XLM, etc.)
    """

    print(f"xxxxxxxx-withdraw-{coin.lower()}-binance-async (IPv4 forced)-xxxxxxxx")

    base_url = "https://api.binance.us"
    endpoint = "/sapi/v1/capital/withdraw/apply"

    timestamp = int(time.time() * 1000)

    # Build params
    params = f"coin={coin}&address={address}&amount={amount:.6f}&timestamp={timestamp}"
    if network:
        params += f"&network={network}"
    if address_tag:
        params += f"&addressTag={address_tag}"

    # Sign the request
    signature = hmac.new(
        api_secret.encode(),
        params.encode(),
        hashlib.sha256
    ).hexdigest()

    url = f"{base_url}{endpoint}?{params}&signature={signature}"
    headers = {"X-MBX-APIKEY": api_key}

    # Force IPv4 resolver (prevents IPv6 DNS issues)
    connector = aiohttp.TCPConnector(family=socket.AF_INET)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(url, headers=headers) as resp:
            data = await resp.json()
            print("Withdraw response:", data)
            return data


# ==========================
# 🔹 CRYPTO.COM TRADING
# ==========================
CRYPTO_BASE = "https://api.crypto.com/v2"
CRYPTO_KEY_PUBLIC = "TNHEKerJALctgUcQZDmky3"
CRYPTO_KEY_PRIVATE = "cxakp_UpCZCeUQGjF3JXHvCj444"

def crypto_sign_v2(req):
    r = req.copy()
    r.pop("sig", None)
    payload = json.dumps(r, separators=(',', ':'), sort_keys=True)
    return hmac.new(
        CRYPTO_KEY_PRIVATE.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()


async def buy_token_crypto(amount_quote, token_pair="XLM_USDT"):
    """Buy base token using quote asset (V2)."""
    url = f"{CRYPTO_BASE}/private/create-order"
    nonce = int(time.time() * 1000)

    params = {
        "instrument_name": token_pair,
        "side": "BUY",
        "type": "MARKET",
        "notional": str(amount_quote)  # spend this much quote currency
    }

    req = {
        "id": nonce,
        "method": "private/create-order",
        "api_key": CRYPTO_KEY_PUBLIC,
        "params": params,
        "nonce": nonce
    }
    req["sig"] = crypto_sign_v2(req)

    headers = {"Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=req, headers=headers) as resp:
            data = await resp.json()
            print("=== BUY RESPONSE ===")
            print(json.dumps(data, indent=2))
            return data


async def sell_token(amount_base: str, instrument="XLM_USDT"):
    url = f"{CRYPTO_BASE}/private/create-order"
    nonce = int(time.time() * 1000)
    req = {
        "id": nonce,
        "method": "private/create-order",
        "api_key": CRYPTO_KEY_PUBLIC,
        "params": {
            "instrument_name": instrument,
            "side": "SELL",
            "type": "MARKET",
            "quantity": amount_base  # must be string
        },
        "nonce": nonce
    }
    req["sig"] = crypto_sign_v2(req)
    headers = {"Content-Type": "application/json"}

    print(f"{req}")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=req, headers=headers) as resp:
            data = await resp.json()
            print(json.dumps(data, indent=2))
            return data
        
# ==========================
# 🔹 Helper: OKX Trade
# ==========================

OKX_BASE_URL = "https://app.okx.com"
from datetime import datetime, timezone

# ==========================
# 🔹 Helper: Sign OKX requests
# ==========================
def okx_sign(secret_key, timestamp, method, request_path, body=""):
    message = f"{timestamp}{method.upper()}{request_path}{body}"
    # h = hmac.new(OKX_KEY_PRIVATE.encode(), message.encode(), hashlib.sha256)
    # return base64.b64encode(h.digest()).decode()

    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    return base64.b64encode(d)

def okx_get_server_time_iso():
    r = requests.get(f"{OKX_BASE_URL}/api/v5/public/time")
    ts = int(r.json()["data"][0]["ts"]) / 1000.0  # seconds with decimals
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    # OKX expects ISO string with milliseconds and 'Z'
    return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

# ==========================
# 🔹 BUY Token (MARKET)
# ==========================
async def buy_token_okx(api_key, api_secret, passphrase, inst_id="XRP-USDT", amount_quote=50):
    print(f"xxxxxxxx-buy-{inst_id}-okx-xxxxxxxx")

    endpoint = "/api/v5/trade/order"
    url = OKX_BASE_URL + endpoint
    ts = okx_get_server_time_iso()

    body = {
        "instId": inst_id,
        "tdMode": "cash",
        "side": "buy",
        "ordType": "market",
        "sz": str(amount_quote)  # amount in base currency
    }

    body_json = json.dumps(body)
    sign = okx_sign(api_secret, ts, "POST", endpoint, body_json)

    headers = {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": sign.decode(),
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "x-simulated-trading": "0",
    }

    # ✅ Force IPv4 for aiohttp
    connector = aiohttp.TCPConnector(family=socket.AF_INET)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(url, headers=headers, data=body_json) as resp:
            data = await resp.json()
            print("Buy response:", data)
            return data


# ==========================
# 🔹 SELL Token (MARKET)
# ==========================
async def sell_token_okx(api_key, api_secret, passphrase, inst_id="XLM-USDT", amount_base=0.01):
    """
    Market sell on OKX (base currency based).
    Example: Sell 0.01 ETH in ETH-USDT.
    """
    print(f"xxxxxxxx-sell-{inst_id}-okx-xxxxxxxx")

    endpoint = "/api/v5/trade/order"
    url = OKX_BASE_URL + endpoint
    timestamp = str(time.time())

    body = {
        "instId": inst_id,
        "tdMode": "cash",
        "side": "sell",
        "ordType": "market",
        "sz": str(amount_base)
    }

    # Use server time in ISO format for both
    ts = okx_get_server_time_iso()

    body_json = json.dumps(body)
    sign = okx_sign(api_secret, ts, "POST", endpoint, body_json)
    sign_str = sign.decode() if isinstance(sign, bytes) else sign

    header = {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": sign_str,
        "OK-ACCESS-TIMESTAMP": ts,  # same as used in signing
        "OK-ACCESS-PASSPHRASE": passphrase,
        "x-simulated-trading": "0",
    }

    # ✅ Force IPv4 for aiohttp
    connector = aiohttp.TCPConnector(family=socket.AF_INET)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(url, headers=header, data=body_json) as resp:
            data = await resp.json()
            print("Sell response:", data)
            return data

# ==========================
# 🔹 WITHDRAW Token
# ==========================
async def withdraw_okx(api_key, api_secret, passphrase, coin, amount, to_addr, network=None, fee=None, dest=4):
    """
    Asynchronously withdraw tokens from OKX to external address.

    Parameters:
        coin (str): e.g. 'USDT', 'BTC', 'ETH'
        amount (float): Amount to withdraw
        to_addr (str): Destination address
        network (str): e.g. 'ETH', 'TRX', 'BSC', etc.
        fee (float): Withdrawal fee (optional)
        dest (int): 3 for internal transfer, 4 for external blockchain withdrawal
    """
    print(f"xxxxxxxx-withdraw-{coin.lower()}-okx-async (IPv4 forced)-xxxxxxxx")

    endpoint = "/api/v5/asset/withdrawal"
    url = OKX_BASE_URL + endpoint
    timestamp = str(time.time())

    body = {
        "ccy": coin,
        "amt": str(amount),
        "dest": str(dest),
        "toAddr": to_addr
    }

    if network:
        body["chain"] = network
    if fee:
        body["fee"] = str(fee)

    body_json = json.dumps(body)
    sign = okx_sign(api_secret, timestamp, "POST", endpoint, body_json)

    headers = {
        "OK-ACCESS-KEY": api_key,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "Content-Type": "application/json"
    }

    # ✅ Force IPv4 (for reliability)
    connector = aiohttp.TCPConnector(family=socket.AF_INET)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(url, headers=headers, data=body_json) as resp:
            data = await resp.json()
            print("Withdraw response:", data)
            return data


# -------------------------------
# EXAMPLE USAGE
# -------------------------------
if __name__ == "__main__":
    # --- Kraken API ---
    kraken_api_key = "F4LpC0xPGQo4DNXBQVsd48uUKE6HaRH78CapiRl8y+LuUHwehhMuJT45"
    kraken_api_secret = "RkpS3CiplIeN7Czwnv0oCMKf0WSUbOK6dE2dyqwSQowBBxrcj6lyLQcY0Z+dKrioQYdMtw21/j5FJGmHEYkwfg=="

    # --- Binance API ---
    binance_api_key = "dsIJAWTBB0gezwo75sFG5mcZPN2gFN6S5D7t1v8xyigp8pLxiJClnCLstcqlsekY"
    binance_api_secret = "YPgwiRF3IjzXuXVffnKHeRhWQCpcH2LPCg68ZgoUQtWXlglOBpRxRU4mpnlzGatQ"
    
    crypto_api_key = "TNHEKerJALctgUcQZDmky3"
    crypto_api_secret = "cxakp_UpCZCeUQGjF3JXHvCj444j"
    
    okx_api_key = "eb17c856-df19-42a4-a767-7278bf2a5138"
    okx_api_secret = "8F67F3B6E55C19B11687FFE01C8D25BA"
    okx_passphrase = "Balloutpaul3!"

    # Amount in USDT to spend
    amount_to_spend = 20  # e.g., 50 USDT

    #------------Kraken-----------
    # kraken_order = buy_xrp_kraken(kraken_api_key, kraken_api_secret, amount_to_spend)
    # buy_usdt_kraken(kraken_api_key, kraken_api_secret, 19.8)
    # sell_xrp_kraken(crypto_api_key, kraken_api_secret, 3)
    # status = check_withdraw_status(kraken_api_key, kraken_api_secret, asset="XRP")
    # async def run_async_withdraw_kraken():
    #     await withdraw_xrp_kraken(kraken_api_key, kraken_api_secret, 10.0, "2nd Mev bots")   
    # asyncio.run(run_async_withdraw_kraken())
    # async def run_async_sell_kraken():
    #     await sell_xrp_kraken(kraken_api_key, kraken_api_secret, 20)   
    # asyncio.run(run_async_sell_kraken())
    # async def run_async_buy_kraken():
    #      await buy_xrp_kraken(kraken_api_key, kraken_api_secret, amount_to_spend) 
    # asyncio.run(run_async_buy_kraken())

    #------------Binance-----------
    
    # async def run_async_buy_binance():
    #     await buy_xrp_binance(binance_api_key, binance_api_secret, amount_usdt=30.0)       
    # asyncio.run(run_async_buy_binance())
    
    # async def run_async_sell_binance():
    #     await sell_xrp_binance(binance_api_key, binance_api_secret, 5.0)       
    # asyncio.run(run_async_sell_binance())
    # sell_xrp_binance(binance_api_key, binance_api_secret, 40)
    #buy_xrp_binance(binance_api_key, binance_api_secret, amount_to_spend)
    
    # async def run_async_withdraw_binance():
    #     await withdraw_binance(binance_api_key, binance_api_secret, 10, "rLHzPsX6oXkzU2qL12kHCH8G8cnZv1rBJh", "2486487676")
    # asyncio.run(run_async_withdraw_binance())
    
    #------------OKX-----------
    # async def run_async_buy_okx():
    #     await buy_token_okx(okx_api_key, okx_api_secret, okx_passphrase, inst_id="XLM-USDT", amount_quote=amount_to_spend)
    # asyncio.run(run_async_buy_okx())
    # async def run_async_sell_okx():
    #     await sell_token_okx(okx_api_key, okx_api_secret, okx_passphrase, inst_id="USDC-USDT", amount_base=49)
    # asyncio.run(run_async_sell_okx())
    # async def run_async_withdraw_okx():
    #     await withdraw_okx(okx_api_key, okx_api_secret, okx_passphrase, "XRP", 10.0, "rLHzPsX6oXkzU2qL12kHCH8G8cnZv1rBJh", network="XRP", address_tag="2486487676")
    # asyncio.run(run_async_withdraw_okx())
    
    #--------------Crypto-------------
    # async def run_async_buy_crypto():
    #     res = await buy_token_crypto(crypto_api_key, crypto_api_secret, amount_quote=amount_to_spend, token_pair="XLM_USDT")
    #     print(f"Buy result: {res}")
    # asyncio.run(run_async_buy_crypto())
    # async def run_async_sell_crypto():
    #     res = await sell_token(amount_base="30", instrument="XLM_USDT")
    #     print(f"Sell result: {res}")
    # asyncio.run(run_async_sell_crypto())
    # buy_token_crypto(crypto_api_key, crypto_api_secret, amount_quote=amount_to_spend, token_pair="XRP_USDT")
    # sell_token_crypto(crypto_api_key, crypto_api_secret, amount_base=20.0, token_pair="XRP_USDT")
    
    import aiohttp, asyncio, time, json, hmac, hashlib

    CRYPTO_BASE = "https://api.crypto.com/v2"
    CRYPTO_KEY_PUBLIC = "TNHEKerJALctgUcQZDmky3"
    CRYPTO_KEY_PRIVATE = "cxakp_UpCZCeUQGjF3JXHvCj444j"

    def crypto_sign_v2(req):
        r = req.copy()
        r.pop("sig", None)
        payload = json.dumps(r, separators=(',', ':'), sort_keys=True)
        return hmac.new(
            CRYPTO_KEY_PRIVATE.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

    async def sell_xlm(amount: int):
        url = f"{CRYPTO_BASE}/private/create-order"
        nonce = int(time.time() * 1000)
        req = {
            "id": nonce,
            "method": "private/create-order",
            "api_key": CRYPTO_KEY_PUBLIC,
            "params": {
                "instrument_name": "XLM_USDT",
                "side": "SELL",
                "type": "MARKET",
                "quantity": str(amount)  # must be string
            },
            "nonce": nonce
        }
        req["sig"] = crypto_sign_v2(req)
        headers = {"Content-Type": "application/json"}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=req, headers=headers) as resp:
                data = await resp.json()
                print(json.dumps(data, indent=2))
                return data

    # Example usage
    asyncio.run(sell_xlm(1))


    # CRYPTO_BASE = "https://api.crypto.com/exchange/v1"  # ✅ Use v1 for public endpoints

    # async def get_instruments():
    #     async with aiohttp.ClientSession() as session:
    #         async with session.get(f"{CRYPTO_BASE}/public/get-instruments") as resp:
    #             data = await resp.json()
    #             return data

    # # Test
    # instruments = asyncio.run(get_instruments())
    # print(f"{instruments}")
    # for i in instruments.get("result", []):
    #     print(i["instrument_name"])



