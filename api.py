import os
import requests
from flask import Flask
from bs4 import BeautifulSoup

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

    soup = BeautifulSoup(response.text, "html.parser")

    prices = {
        "gold": "نامشخص",
        "coin": "نامشخص",
        "dollar": "نامشخص",
        "euro": "نامشخص",
        "bitcoin": "نامشخص"
    }

    # پیدا کردن قیمت‌ها از جدول/ویجت
    rows = soup.find_all("tr")

    for row in rows:
        text = row.get_text(" ", strip=True)

        if "طلای 18" in text or "طلای ۱۸" in text:
            prices["gold"] = text

        elif "سکه امامی" in text:
            prices["coin"] = text

        elif "دلار" in text:
            prices["dollar"] = text

        elif "یورو" in text:
            prices["euro"] = text

        elif "بیت کوین" in text or "بیت‌کوین" in text:
            prices["bitcoin"] = text

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

🟡 طلای ۱۸ عیار: {prices["gold"]}
🪙 سکه امامی: {prices["coin"]}
💵 دلار: {prices["dollar"]}
💶 یورو: {prices["euro"]}
₿ بیت‌کوین: {prices["bitcoin"]}

🔄 آخرین بروزرسانی از TGJU
"""

    send_message(message)

    return "Message sent!"
