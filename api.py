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
        pattern = rf"{re.escape(name)}\s+([\d,]+)\s*\(([-+]?\d+(?:\.\d+)?)%\)"
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
            "User-Agent": "Mirza-Bot/1.0"
        }
    )

    response.raise_for_status()

    data = response.json()

    bitcoin_price = data["bitcoin"]["usd"]
    bitcoin_change = data["bitcoin"].get("usd_24h_change", 0)

    ethereum_price = data["ethereum"]["usd"]
    ethereum_change = data["ethereum"].get("usd_24h_change", 0)

    return {
        "bitcoin": (bitcoin_price, bitcoin_change),
        "ethereum": (ethereum_price, ethereum_change)
    }


# -----------------------------
# دریافت شاخص ترس و طمع
# -----------------------------
def get_fear_greed():

    url = "https://api.alternative.me/fng/?limit=1"

    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mirza-Bot/1.0"
        }
    )

    response.raise_for_status()

    data = response.json()["data"][0]

    value = data["value"]
    classification = data["value_classification"]

    return value, classification


# -----------------------------
# نمایش درصد تغییر
# -----------------------------
def change_icon(change):

    try:
        value = float(change)

        if value > 0:
            return f"🟢 +{value:.2f}%"

        if value < 0:
            return f"🔴 {value:.2f}%"

        return "⚪ 0.00%"

    except:
        return "⚪ 0.00%"


# -----------------------------
# ارسال پیام به تلگرام
# -----------------------------
def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    response = requests.post(
        url,
        json=payload,
        timeout=20
    )

    response.raise_for_status()

    return response.json()


# -----------------------------
# ساخت پیام
# -----------------------------
def build_message():

    tgju = get_tgju_prices()
    crypto = get_crypto_prices()
    fear_value, fear_text = get_fear_greed()

    gold_price, gold_change = tgju["gold"]
    coin_price, coin_change = tgju["coin"]
    dollar_price, dollar_change = tgju["dollar"]
    euro_price, euro_change = tgju["euro"]

    bitcoin_price, bitcoin_change = crypto["bitcoin"]
    ethereum_price, ethereum_change = crypto["ethereum"]

    now = datetime.now(
        ZoneInfo("Asia/Tehran")
    ).strftime("%Y/%m/%d - %H:%M")

    message = f"""
📊 MIRZA

━━━━━━━━━━━━━━━━━━

🏦 بازار ایران

🟡 طلای ۱۸
💰 {gold_price} ریال
{change_icon(gold_change)}

🪙 سکه امامی
💰 {coin_price} ریال
{change_icon(coin_change)}

💵 دلار
💰 {dollar_price} ریال
{change_icon(dollar_change)}

💶 یورو
💰 {euro_price} ریال
{change_icon(euro_change)}

━━━━━━━━━━━━━━━━━━

🌐 رمزارز

₿ بیت‌کوین
💰 ${bitcoin_price:,.2f}
{change_icon(bitcoin_change)}

Ξ اتریوم
💰 ${ethereum_price:,.2f}
{change_icon(ethereum_change)}

━━━━━━━━━━━━━━━━━━

😨 شاخص ترس و طمع

🎯 {fear_value} — {fear_text}

━━━━━━━━━━━━━━━━━━

🕒 آخرین بروزرسانی:
{now}

📌 منابع:
TGJU | CoinGecko | Alternative.me
"""

    return message.strip()


# -----------------------------
# صفحه اصلی
# -----------------------------
@app.route("/")
def home():
    return "Mirza Bot is running!"


# -----------------------------
# ارسال دستی / زمان‌بندی
# -----------------------------
@app.route("/send")
def send():

    try:
        message = build_message()
        result = send_telegram(message)

        return {
            "status": "success",
            "message": "Message sent!",
            "telegram": result
        }

    except Exception as e:

        return {
            "status": "error",
            "error": str(e)
        }, 500


# -----------------------------
# تست دریافت قیمت‌ها
# -----------------------------
@app.route("/prices")
def prices():

    try:
        return {
            "tgju": get_tgju_prices(),
            "crypto": get_crypto_prices(),
            "fear_greed": get_fear_greed()
        }

    except Exception as e:

        return {
            "status": "error",
            "error": str(e)
        }, 500


# -----------------------------
# اجرای برنامه
# -----------------------------
if __name__ == "__main__":
    app.run()
