import os
import re
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")


# -----------------------------
# دریافت قیمت‌های TGJU
# -----------------------------
def get_tgju_prices():
    url = "https://www.tgju.org/widget/get/market-data"

    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )
    response.raise_for_status()

    text = response.text

    def find_price(name):
        pattern = rf"{re.escape(name)}\s+([\d,]+)\s*([-+]?\d+(?:\.\d+)?)%"
        match = re.search(pattern, text)

        if match:
            price = match.group(1)
            change = match.group(2)

            return price, change

        return "نامشخص", "0"

    return {
        "gold": find_price("طلا ۱۸"),
        "coin": find_price("سکه"),
        "dollar": find_price("دلار"),
        "euro": find_price("یورو")
    }


# -----------------------------
# دریافت بیت‌کوین و اتریوم
# از CoinGecko
# -----------------------------
def get_crypto_prices():

    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum"
        "&vs_currencies=usd"
        "&include_24hr_change=true"
    )

    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mirza-Bot
