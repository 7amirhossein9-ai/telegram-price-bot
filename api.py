import os
import re
import requests
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")


def get_prices():
    url = "https://www.tgju.org/widget/get/market-data"

    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=15
    )

    response.raise_for_status()
    text = response.text

    def find_price(name):
        # پیدا کردن نام بازار و اولین عدد بعد از آن
        pattern = rf"{re.escape(name)}.*?([\d,]+)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)

        if match:
            return match.group(1)

        return "نامشخص"

    prices = {
        "gold18": find_price("طلا ۱۸"),
        "coin": find_price("سکه"),
        "dollar": find_price("دلار"),
        "euro": find_price("یورو"),
        "bitcoin": find_price("بیت کوین")
    }

    return prices


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=15
    )

    response.raise_for_status()


@app.route("/")
def home():
    return "Mirza Bot is running!"


@app.route("/send")
def send():

    prices = get_prices()

    message = f"""📊 Mirza Market

🟡 طلای ۱۸ عیار: {prices['gold18']}
🪙 سکه امامی: {prices['coin']}
💵 دلار: {prices['dollar']}
💶 یورو: {prices['euro']}
₿ بیت‌کوین: {prices['bitcoin']}

🔄 آخرین بروزرسانی از TGJU"""

    send_message(message)

    return "Message sent!"
