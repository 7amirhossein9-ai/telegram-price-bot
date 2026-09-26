import os
import re
import requests
from flask import Flask, jsonify

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

TGJU_URL = "https://www.tgju.org/widget/get/market-data"


# =========================
# دریافت قیمت‌ها
# =========================

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

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    def find_price(name):

        pattern = rf"{name}\s+([\d,]+)\s*\(([-+]?\d+(?:\.\d+)?)%\)"

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


# =========================
# آیکون تغییر قیمت
# =========================

def change_icon(change):

    try:
        value = float(change)

        if value > 0:
            return "🟢"

        if value < 0:
            return "🔴"

        return "⚪"

    except:
        return "⚪"


# =========================
# ارسال پیام به تلگرام
# =========================

def send_message(text):

    if not BOT_TOKEN:
        raise Exception("BOT_TOKEN تنظیم نشده است.")

    if not CHAT_ID:
        raise Exception("CHAT_ID تنظیم نشده است.")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=20
    )

    response.raise_for_status()

    return response.json()


# =========================
# صفحه اصلی
# =========================

@app.route("/")
def home():

    return "📊 MIRZA Bot is running!"


# =========================
# ارسال یک پیام قیمت
# =========================

@app.route("/send")
def send():

    prices = get_prices()

    gold, gold_change = prices["gold18"]
    coin, coin_change = prices["coin"]
    dollar, dollar_change = prices["dollar"]
    euro, euro_change = prices["euro"]
    bitcoin, bitcoin_change = prices["bitcoin"]

    message = f"""
<b>╔══════════════════════╗</b>
<b>           📊 MIRZA</b>
<b>╚══════════════════════╝</b>

🟡 <b>طلای ۱۸ عیار</b>
💰 <b>{gold}</b>    {change_icon(gold_change)} <b>{gold_change}%</b>

🪙 <b>سکه امامی</b>
💰 <b>{coin}</b>    {change_icon(coin_change)} <b>{coin_change}%</b>

💵 <b>دلار</b>
💰 <b>{dollar}</b>    {change_icon(dollar_change)} <b>{dollar_change}%</b>

💶 <b>یورو</b>
💰 <b>{euro}</b>    {change_icon(euro_change)} <b>{euro_change}%</b>

₿ <b>بیت‌کوین</b>
💰 <b>{bitcoin}</b>    {change_icon(bitcoin_change)} <b>{bitcoin_change}%</b>

━━━━━━━━━━━━━━━━━━━━

🔄 <i>آخرین بروزرسانی از TGJU</i>
"""

    send_message(message)

    return "Message sent successfully! ✅"


# =========================
# مشاهده قیمت‌ها
# =========================

@app.route("/prices")
def prices():

    return jsonify(get_prices())


# =========================
# اجرای محلی
# =========================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
