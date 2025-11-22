import time
import hmac
import hashlib
import base64
import requests
import urllib.parse
import json

import aiohttp
import asyncio

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
# OKX API config
# ------------------------------
with open('keys/okx.key') as f:
    okx_key = json.load(f)

OKX_KEY_PUBLIC = okx_key['public'].strip()
OKX_KEY_PRIVATE = okx_key['private'].strip()
OKX_PASSPHRASE = okx_key['passphrase'].strip()
OKX_BASE = "https://app.okx.com"


# =====================================================================
# OKX
# =====================================================================
from datetime import datetime, timezone

USE_DEMO = False  # Set True if your key is from Demo Trading

def okx_signature(timestamp, method, request_path, body=""):
    """
    Properly generate an OKX API signature and return it as a UTF-8 string.
    """
    message = f"{timestamp}{method.upper()}{request_path}{body}"
    mac = hmac.new(
        OKX_KEY_PRIVATE.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    )
    d = mac.digest()
    # ✅ FIX: Decode to str
    return base64.b64encode(d).decode("utf-8")

# --- Get server timestamp in ISO format (milliseconds, UTC) ---
def okx_get_server_time_iso():
    """
    Get OKX server time in ISO8601 format with milliseconds and 'Z'.
    """
    r = requests.get(f"{OKX_BASE}/api/v5/public/time", timeout=10)
    ts = int(r.json()["data"][0]["ts"]) / 1000.0
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

# --- Get account balances ---
def okx_get_balances():

    path = "/api/v5/account/balance"
    url = OKX_BASE + path

    # Use server time in correct ISO format
    ts = okx_get_server_time_iso()

    # Empty body for GET
    body = ""
    sign = okx_signature(ts, "GET", path, body)

    # headers = {
    #     "OK-ACCESS-KEY": OKX_KEY_PUBLIC,
    #     "OK-ACCESS-SIGN": sign,
    #     "OK-ACCESS-TIMESTAMP": ts,
    #     "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
    #     "Content-Type": "application/json",
    #     "x-simulated-trading": "1" if USE_DEMO else "0",
    # }

    header = dict()
    header["Content-Type"] = "application/json"
    header["OK-ACCESS-KEY"] = OKX_KEY_PUBLIC
    header["OK-ACCESS-SIGN"] = sign
    header["OK-ACCESS-TIMESTAMP"] = ts
    header["OK-ACCESS-PASSPHRASE"] = OKX_PASSPHRASE
    header['x-simulated-trading'] = "1" if USE_DEMO else "0"

    r = requests.get(url, headers=header)
    data = r.json()
    # print("Response:", json.dumps(data, indent=2))
    return data


def okx_total_usdt():
    print("----------Total asset in OKX----------")
    
    balances_resp = okx_get_balances()
    data_list = balances_resp.get("data", [])

    if not data_list:
        print("No balance data found.")
        return 0.0, []

    details_list = data_list[0].get("details", [])
    if not details_list:
        print("No asset details found.")
        return 0.0, []

    tickers = requests.get(f"{OKX_BASE}/api/v5/market/tickers?instType=SPOT").json()
    ticker_map = {t["instId"]: float(t["last"]) for t in tickers.get("data", [])}

    total = 0.0
    details = []

    for b in details_list:
        coin = b.get("ccy")
        amt = float(b.get("availBal", 0))
        if amt <= 0:
            continue

        if coin == "USDT":
            val = amt
        else:
            continue
            pair = f"{coin}-USDT"
            price = ticker_map.get(pair)
            if price is None:
                # If no direct USDT pair, skip or assume 1 for stablecoins
                price = 1.0 if coin in ("USDC", "USD") else 0.0

            val = amt * price

        details.append({"asset": coin, "amount": amt, "value_usdt": val})
        print(f"[OKX] {coin}: {amt} → {val:.2f} USDT")
        total += val

    # print(f"Total portfolio value: {total:.2f} USDT")
    return total, details

def okx_get_token_price(symbol: str):
    """
    Get the latest price for a given trading pair on OKX.
    Automatically tries USDT → USDC → USD if needed.
    Example: 'BTC', 'XLM', 'SOL', 'ETH'
    """
    try:
        # Normalize input symbol
        base = symbol.upper().replace("/", "-").split("-")[0]

        # Try multiple quote currencies
        quotes = ["USDT", "USDC", "USD"]
        for quote in quotes:
            inst_id = f"{base}-{quote}"
            url = f"{OKX_BASE}/api/v5/market/ticker?instId={inst_id}"

            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()

            # Debug print
            # print(f"Raw ticker data for {inst_id}: {json.dumps(data, indent=2)}")

            if data.get("code") == "0" and "data" in data and len(data["data"]) > 0:
                ticker_info = data["data"][0]
                price = float(ticker_info.get("last", 0.0))
                # print(f"[OKX] {inst_id} → {price:.6f}")
                return price

        print(f"⚠️ No valid price found for {base} (tried {', '.join(quotes)})")
        return 0.0

    except Exception as e:
        print(f"❌ Error fetching {symbol} price: {e}")
        return 0.0
    
def okx_get_deposit_address(coin: str):
    """
    Get deposit address for a given token on OKX.
    Example: okx_get_deposit_address("XLM")
    Returns {'address': '...', 'tag': '...'} if available.
    """
    try:
        path = f"/api/v5/asset/deposit-address?ccy={coin.upper()}"
        url = OKX_BASE + path

        ts = okx_get_server_time_iso()
        body = ""
        sign = okx_signature(ts, "GET", path, body)

        headers = {
            "OK-ACCESS-KEY": OKX_KEY_PUBLIC,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
            "Content-Type": "application/json",
            "x-simulated-trading": "1" if USE_DEMO else "0",
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

        print(f"[OKX] Deposit address for {coin}: {address}, tag: {tag}")
        return {"address": address, "tag": tag}

    except Exception as e:
        print(f"❌ Error fetching OKX deposit address for {coin}: {e}")
        return {"address": None, "tag": None}

def okx_transfer_to_funding(ccy="XLM", amt="30"):
    path = "/api/v5/asset/transfer"
    url = OKX_BASE + path

    ts = okx_get_server_time_iso()
    body_data = {
        "ccy": ccy,
        "amt": str(amt),
        "from": "18",  # 18 = Trading account
        "to": "6",     # 6 = Funding account
        "type": "0"    # 0 = Internal transfer
    }

    body = json.dumps(body_data)
    sign = okx_signature(ts, "POST", path, body)

    headers = {
        "OK-ACCESS-KEY": OKX_KEY_PUBLIC,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type": "application/json",
    }

    r = requests.post(url, headers=headers, data=body)
    print("Transfer response:", r.json())
    return r.json()


def okx_withdraw(coin: str, amount: float, to_address: str, chain: str = None, tag: str = None):
    coin = coin.upper()

    if coin in ["XLM", "XRP", "EOS"] and not tag:
        raise ValueError(f"{coin} withdrawal requires a memo/tag.")

    # Combine address:tag for XLM/XRP/EOS
    if coin in ["XLM", "XRP", "EOS", "USDT"]:
        to_address = f"{to_address}:{tag}"
        chain = None  # ✅ omit chain for these coins

    # Round amount
    amount = round(amount, 7 if coin in ["XLM", "XRP"] else 4)

    body_data = {
        "ccy": coin,
        "amt": str(amount),
        "dest": "4",
        "toAddr": to_address
    }

    # Only add chain for non-tag-based coins
    if chain and coin not in ["XLM", "XRP", "EOS"]:
        body_data["chain"] = chain

    # Sign & send
    ts = okx_get_server_time_iso()
    body = json.dumps(body_data)
    sign = okx_signature(ts, "POST", "/api/v5/asset/withdrawal", body)

    headers = {
        "OK-ACCESS-KEY": OKX_KEY_PUBLIC,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type": "application/json",
    }

    print("➡️ Payload:", body_data)
    r = requests.post(OKX_BASE + "/api/v5/asset/withdrawal", headers=headers, data=body)
    data = r.json()
    print("🔁 Response:", data)

    return data


# ------------------------------
# 🔹 Async Place Order Functions
# ------------------------------

async def okx_place_order(symbol: str, side: str, amount: float, price: float = None, market: bool = True):
    path = "/api/v5/trade/order"
    url = OKX_BASE + path

    payload = {
        "instId": symbol.upper().replace("/", "-"),
        "tdMode": "cash",
        "side": side.lower(),
        "ordType": "market" if market else "limit",
        "sz": f"{amount:.6f}"
    }
    if not market and price is not None:
        payload["px"] = f"{price:.6f}"

    ts = okx_get_server_time_iso()
    body = json.dumps(payload)
    sign = okx_signature(ts, "POST", path, body)

    headers = {
        "OK-ACCESS-KEY": OKX_KEY_PUBLIC,
        "OK-ACCESS-SIGN": sign.decode() if isinstance(sign, bytes) else sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type": "application/json",
        "x-simulated-trading": "1" if USE_DEMO else "0",
    }

    # ✅ Force IPv4
    connector = aiohttp.TCPConnector(family=socket.AF_INET)

    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(url, headers=headers, data=body, timeout=10) as resp:
                data = await resp.json()
                if data.get("code") != "0":
                    raise ValueError(f"Failed to place order {side} {symbol}: {data}")

                ord_id = data["data"][0].get("ordId")
                print(f"✅ Order placed: {side.upper()} {symbol} | Amount: {amount} | Order ID: {ord_id}")
                return data

    except Exception as e:
        print(f"❌ Error placing {side} order for {symbol}: {e}")
        return {"code": "-1", "error": str(e)}


async def okx_buy_token(symbol: str, amount: float, price: float = None, market: bool = True):
    """Async shortcut to place a buy order."""
    return await okx_place_order(symbol, "buy", amount, price, market)


async def okx_sell_token(symbol: str, amount: float, price: float = None, market: bool = True):
    """Async shortcut to place a sell order."""
    return await okx_place_order(symbol, "sell", amount, price, market)

def okx_get_currencies():
    path = "/api/v5/asset/currencies"
    url = OKX_BASE + path
    ts = okx_get_server_time_iso()
    body = ""
    sign = okx_signature(ts, "GET", path, body)

    headers = {
        "OK-ACCESS-KEY": OKX_KEY_PUBLIC,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type": "application/json",
        "x-simulated-trading": "0"
    }

    r = requests.get(url, headers=headers)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "0":
        raise ValueError(f"Error fetching currencies: {data}")
    return data["data"]


if __name__ == "__main__":
    res = asyncio.run(okx_sell_token("XRP-USDT", 12.91))
    print(res)
    
    # res = okx_get_deposit_address("AVAX")
    # print(res)
    
     # chains_resp = okx_get_chains("XLM")
    # print(chains_resp)
    
    # res_bal = okx_get_balances()
    # print(f"Balance : {res_bal}")
    
    # currencies = okx_get_currencies()
    # xlm_info = next((c for c in currencies if c["ccy"] == "XLM"), None)
    # print(xlm_info)

    
    # balances = okx_get_balances()
    # print(f"Balance : {balances}")
    # xlm_avail = next((d['availBal'] for d in balances['data'][0]['details'] if d['ccy']=='XLM'), None)
    # print("Available XLM:", xlm_avail)
    
    # okx_transfer_to_funding("XLM", "21.1")
    
    # res = okx_withdraw(
    #     coin="USDT",
    #     amount=10,
    #     to_address="0x808e798e4b0e91d843082f7f825a16267cc250dd",
    #     chain="ETH",  # must match OKX's exact chain name
    #     tag=None              # required for XLM
    # )
    # print(f"Withdraw : {res}")


    # print(res)
    # res = okx_withdraw_xlm(
    #     amount=30.0, 
    #     to_address="GC7ANIOVX27Z6CL3U2PSVWDCJUEEEUKNIYSFGU2BXPROE3L7Q5GNI7CN", 
    #     tag="2465307129"
    # )
    # print(res)

 