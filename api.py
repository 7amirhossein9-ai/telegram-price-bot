import os
import requests
from flask import Flask

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    })

@app.route("/")
def home():
    return "Mirza Bot is running!"

@app.route("/send")
def send():
    # فعلاً پیام تست برای اطمینان از اتصال
    message = """📊 <b>Mirza Market</b>

🟡 طلای ۱۸ عیار: در حال دریافت
🪙 سکه امامی: در حال دریافت
💵 دلار: در حال دریافت
₿ بیت‌کوین: در حال دریافت

🔄 سیستم فعال است."""

    send_message(message)
    return "Message sent!"
