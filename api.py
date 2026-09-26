import os
import re
import requests
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

TGJU_URL = "https://www.tgju.org/widget/get/market-data"


def get_prices():
    response = requests.get(
        TGJU_URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=20
    )

    response.raise_for_status()
    html = response.text

    # استخراج اطلاعات بازار از متن صفحه
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    def find_price(name):
        pattern = rf"{name}\s+([\d,]+)\s*\(([-\d.]+)%\)"
        match = re.search(pattern, text)

        if match:
            return match.group(1), match.group(2)

        return "نامشخص", "نامشخص"

    return {
        "gold18": find_price("طلا ۱۸"),
        "coin": find_price("سکه"),
        "dollar": find_price("دلار"),
        "euro": find_price("یورو"),
        "bitcoin": find_price("بیت کوین")
    }


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=20
    )

    response.raise_for_status()


@app.route("/")
def home():
    return "Mirza Bot is running!"


@app.route("/send")
def send():
    prices = get_prices()

    gold, gold_change = prices["gold18"]
    coin, coin_change = prices["coin"]
    dollar, dollar_change = prices["dollar"]
    euro, euro_change = prices["euro"]
    bitcoin, bitcoin_change = prices["bitcoin"]

    message = f"""📊 <b>Mirza Market</b>

🟡 <b>طلای ۱۸ عیار:</b> {gold}
📈 تغییر: {gold_change}٪

🪙 <b>سکه امامی:</b> {coin}
📈 تغییر: {coin_change}٪

💵 <b>دلار:</b> {dollar}
📈 تغییر: {dollar_change}٪

💶 <b>یورو:</b> {euro}
📈 تغییر: {euro_change}٪

₿ <b>بیت‌کوین:</b> {bitcoin}
📈 تغییر: {bitcoin_change}٪

🔄 بروزرسانی از TGJU
"""

    send_message(message)

    return "Message sent successfully!"


@app.route("/prices")
def prices():
    return get_prices()
