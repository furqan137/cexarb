import time
import hmac
import hashlib
import base64
import requests
import urllib.parse
import json

import sys
import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.insert(0, PROJECT_ROOT)

from engines.utils.check_asset_binance import binance_total_usdt, binance_get_price
from engines.utils.check_asset_okx import okx_total_usdt, okx_get_token_price
from engines.utils.check_asset_kraken import kraken_total_usdt, kraken_get_ticker

import socket
import requests.packages.urllib3.util.connection as urllib3_cn

# ==========================
# 🔹 UNIVERSAL UTILS
# ==========================

def allowed_gai_family():
    # Force IPv4
    return socket.AF_INET

urllib3_cn.allowed_gai_family = allowed_gai_family

# =====================================================================
# Combined Total
# =====================================================================
def total_usdt_across_all():
    print("=" * 50)
    total, details = 0.0, []
    bin_total, _ = binance_total_usdt()
    # kraken_total, _ = kraken_total_usdt()
    okx_total_val, _ = okx_total_usdt()
    total = (
            bin_total
            #+ kraken_total
            + okx_total_val
        )
    print(f"\n🔹 Combined USDT total across Binance + OKX: {total:.2f}")
    print("=" * 50)
    return total

def total_asset_prices():
    print("=" * 50)
    bin_price = binance_get_price("XLMUSDT")
    print(f"XLM_price_binance : {bin_price}")
    okx_price = okx_get_token_price("XLM")
    print(f"XLM_price_okx : {okx_price}")
    kraken_price = price=kraken_get_ticker("XXLMZUSD")
    print(f"XLM_price_kraken : {kraken_price}")

if __name__ == "__main__":
    total_usdt_across_all()
    # total_asset_prices()
