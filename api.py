import os
import requests
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")


def get_prices():
    url = "https://www.tgju.org/widget/get/market-data"

    response = requests.get(url, timeout=15)
    response.raise_for_status()

    text = response.text

    # فعلاً داده‌های صفحه را استخراج می‌کنیم
    return text


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=15
    )


@app.route("/")
def home():
    return "Mirza Bot is running!"


@app.route("/send")
def send():
    message = """📊 Mirza Market

🟡 طلای ۱۸ عیار: در حال دریافت
🪙 سکه امامی: در حال دریافت
💵 دلار: در حال دریافت
💶 یورو: در حال دریافت
₿ بیت‌کوین: در حال دریافت

🔄 سیستم فعال است."""

    send_message(message)

    return "Message sent!"
