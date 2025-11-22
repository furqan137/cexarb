import aiohttp
import hmac
import hashlib
import time
import json

# ==========================
# CONFIGURATION
# ==========================
CRYPTO_BASE = "https://api.crypto.com/exchange/v1"
CRYPTO_KEY_PUBLIC = "TNHEKerJALctgUcQZDmky3"
CRYPTO_KEY_PRIVATE = "cxakp_UpCZCeUQGjF3JXHvCj444j"


# ==========================
# SIGNATURE (v1 format)
# ==========================
def crypto_sign(api_key: str, api_secret: str, req_time: int):
    """Generate HMAC SHA256 signature for v1 API."""
    message = api_key + str(req_time)
    sig = hmac.new(
        bytes(api_secret, "utf-8"),
        msg=bytes(message, "utf-8"),
        digestmod=hashlib.sha256
    ).hexdigest().upper()
    return sig


# ==========================
# CORE POST FUNCTION
# ==========================
async def crypto_post(endpoint: str, params: dict = None, private: bool = False):
    """Send POST request to Crypto.com Exchange v1 API."""
    if params is None:
        params = {}

    req_time = int(time.time() * 1000)
    url = f"{CRYPTO_BASE}/{endpoint}"

    headers = {}
    if private:
        sig = crypto_sign(CRYPTO_KEY_PUBLIC, CRYPTO_KEY_PRIVATE, req_time)
        headers = {
            "Content-Type": "application/json",
            "api-key": CRYPTO_KEY_PUBLIC,
            "sig": sig,
            "req-time": str(req_time),
        }

    print(f"\n🔹 POST {url}")
    print(f"🔸 Headers: {headers}")
    print(f"🔸 Params: {json.dumps(params, indent=2)}")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=params) as resp:
            text = await resp.text()
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                result = {"error": text}

            if resp.status != 200:
                print(f"❌ HTTP {resp.status}: {text}")
                return result

            print(f"\n✅ RESPONSE ({endpoint}):")
            print(json.dumps(result, indent=2))
            return result


# ==========================
# ORDER HELPERS
# ==========================
async def create_order(symbol: str, side: str, order_type="LIMIT",
                       price=None, quantity=None):
    """Create a new order (v1)."""
    params = {
        "instrument_name": symbol,
        "side": side.upper(),  # BUY or SELL
        "type": order_type,    # LIMIT or MARKET
    }

    if price is not None:
        params["price"] = str(price)
    if quantity is not None:
        params["quantity"] = str(quantity)

    return await crypto_post("private/create-order", params, private=True)


# ==========================
# TEST FUNCTION
# ==========================
import asyncio

async def test_api():
    print("\n=== Testing Account Summary ===")
    await crypto_post("private/get-account-summary", private=True)

    # Uncomment to test an order
    # print("\n=== Creating Test Order ===")
    await create_order("BTC_USDT", "BUY", order_type="LIMIT", price=50000, quantity=0.001)

asyncio.run(test_api())
