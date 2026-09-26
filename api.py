import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from flask import Flask
from zoneinfo import ZoneInfo


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/130 Safari/537.36"
    )
}


# =========================================================
# HTTP SESSION
# =========================================================

session = requests.Session()
session.headers.update(HEADERS)


# =========================================================
# HELPERS
# =========================================================

def clean_number(value):
    """
    تبدیل عددهای دارای , یا کاراکترهای اضافی به float
    """

    if value is None:
        return None

    value = str(value)

    value = (
        value.replace(",", "")
        .replace("٬", "")
        .replace("٫", ".")
        .replace("%", "")
        .strip()
    )

    value = re.sub(r"[^\d.\-+]", "", value)

    if not value:
        return None

    try:
        return float(value)
    except ValueError:
        return None


def format_price(value):
    """
    نمایش قیمت با جداکننده هزارگان
    """

    if value is None:
        return "نامشخص"

    if float(value).is_integer():
        return f"{int(value):,}"

    return f"{value:,.2f}"


def format_money(value):
    """
    نمایش ارزش پولی به میلیارد تومان
    """

    if value is None:
        return "نامشخص"

    billion_toman = value / 10 / 1_000_000_000

    return f"{billion_toman:,.1f} میلیارد"


def calculate_change(current, previous):
    """
    محاسبه درصد تغییر نسبت به قیمت قبلی
    """

    if current is None or previous is None or previous == 0:
        return None

    return ((current - previous) / previous) * 100


def change_text(change):
    """
    تبدیل درصد تغییر به متن مناسب Telegram
    """

    if change is None:
        return "⚪ نامشخص"

    if change > 0:
        return f"🟢 +{change:.2f}%"

    if change < 0:
        return f"🔴 {change:.2f}%"

    return "⚪ 0.00%"


# =========================================================
# TGJU
# =========================================================

TGJU_PROFILES = {
    "gold": "https://www.tgju.org/profile/geram18",
    "coin": "https://www.tgju.org/profile/sekee",
    "dollar": "https://www.tgju.org/profile/price_dollar_rl",
    "euro": "https://www.tgju.org/profile/price_eur",
}


def get_tgju_current(profile_url):
    """
    دریافت قیمت فعلی از صفحه شاخص TGJU
    """

    response = session.get(
        profile_url,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    text = soup.get_text(" ", strip=True)

    # الگوی:
    # نرخ فعلی:: 2,346,150
    match = re.search(
        r"نرخ فعلی\s*::?\s*([\d,]+)",
        text
    )

    if not match:
        raise ValueError("قیمت فعلی پیدا نشد")

    return clean_number(match.group(1))


def get_tgju_previous_close(profile_url):
    """
    دریافت آخرین قیمت پایانی قبلی از تاریخچه TGJU
    """

    history_url = profile_url.rstrip("/") + "/history"

    response = session.get(
        history_url,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # تمام جدول‌ها را بررسی می‌کنیم
    tables = soup.find_all("table")

    for table in tables:

        rows = table.find_all("tr")

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])

            if len(cells) < 5:
                continue

            values = [
                cell.get_text(" ", strip=True)
                for cell in cells
            ]

            # ساختار تاریخچه TGJU:
            #
            # بازگشایی
            # کمترین
            # بیشترین
            # پایانی
            # میزان تغییر
            # درصد تغییر
            # تاریخ

            closing_price = clean_number(values[4 - 1])

            if closing_price:
                return closing_price

    return None


def get_tgju_prices():
    """
    دریافت قیمت‌های بازار ایران
    """

    result = {}

    for name, url in TGJU_PROFILES.items():

        try:

            current = get_tgju_current(url)

            previous = get_tgju_previous_close(url)

            change = calculate_change(
                current,
                previous
            )

            result[name] = {
                "current": current,
                "previous": previous,
                "change": change,
            }

        except Exception as e:

            print(
                f"TGJU error - {name}: {e}"
            )

            result[name] = {
                "current": None,
                "previous": None,
                "change": None,
            }

    return result


# =========================================================
# CRYPTO
# =========================================================

def get_crypto_prices():

    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum"
        "&vs_currencies=usd"
        "&include_24hr_change=true"
    )

    response = session.get(
        url,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    return {
        "bitcoin": {
            "price": data["bitcoin"]["usd"],
            "change": data["bitcoin"].get(
                "usd_24h_change",
                0
            )
        },

        "ethereum": {
            "price": data["ethereum"]["usd"],
            "change": data["ethereum"].get(
                "usd_24h_change",
                0
            )
        }
    }


# =========================================================
# FEAR & GREED
# =========================================================

def get_fear_greed():

    url = (
        "https://api.alternative.me/fng/"
        "?limit=1"
    )

    response = session.get(
        url,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()["data"][0]

    return {
        "value": int(data["value"]),
        "classification": data["value_classification"]
    }


def fear_emoji(value):

    if value <= 24:
        return "😱"

    if value <= 44:
        return "😨"

    if value <= 55:
        return "😐"

    if value <= 74:
        return "😀"

    return "🤑"


# =========================================================
# TSETMC
# =========================================================

TSETMC_CLIENT_TYPE_URL = (
    "https://cdn.tsetmc.com/api/ClientType/GetClientTypeAll"
)


def get_tsetmc_money_flow():

    try:

        response = session.get(
            TSETMC_CLIENT_TYPE_URL,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        # -------------------------------------------------
        # پیدا کردن لیست اصلی
        # -------------------------------------------------

        records = None

        if isinstance(data, list):
            records = data

        elif isinstance(data, dict):

            for key in [
                "clientTypeAllDto",
                "clientTypeAll",
                "clientType"
            ]:

                if key in data:
                    records = data[key]
                    break

        if not records:
            raise ValueError(
                "داده حقیقی/حقوقی دریافت نشد"
            )

        real_buy = 0
        real_sell = 0

        # -------------------------------------------------
        # جمع خرید و فروش حقیقی کل بازار
        # -------------------------------------------------

        for item in records:

            if not isinstance(item, dict):
                continue

            buy_value = (
                item.get("buy_I_Value")
                or item.get("buyIValue")
                or 0
            )

            sell_value = (
                item.get("sell_I_Value")
                or item.get("sellIValue")
                or 0
            )

            buy_value = clean_number(
                buy_value
            ) or 0

            sell_value = clean_number(
                sell_value
            ) or 0

            real_buy += buy_value
            real_sell += sell_value

        net_flow = real_buy - real_sell

        return {
            "buy": real_buy,
            "sell": real_sell,
            "net": net_flow
        }

    except Exception as e:

        print(
            f"TSETMC error: {e}"
        )

        return {
            "buy": None,
            "sell": None,
            "net": None
        }


# =========================================================
# MONEY FLOW TEXT
# =========================================================

def money_flow_message(flow):

    net = flow.get("net")

    if net is None:
        return (
            "🏦 بورس تهران\n"
            "⚪ اطلاعات ورود و خروج پول در دسترس نیست"
        )

    if net > 0:

        return (
            "🏦 بورس تهران\n\n"
            f"🟢 ورود پول حقیقی\n"
            f"💰 {format_money(net)}"
        )

    if net < 0:

        return (
            "🏦 بورس تهران\n\n"
            f"🔴 خروج پول حقیقی\n"
            f"💰 {format_money(abs(net))}"
        )

    return (
        "🏦 بورس تهران\n\n"
        "⚪ ورود و خروج پول تقریباً برابر"
    )


# =========================================================
# MARKET ITEM
# =========================================================

def market_item(
    title,
    emoji,
    data
):

    if not data:
        return (
            f"{emoji} {title}\n"
            "💰 نامشخص"
        )

    current = data.get("current")
    previous = data.get("previous")
    change = data.get("change")

    return (
        f"{emoji} {title}\n"
        f"💰 {format_price(current)} ریال\n"
        f"📌 قبلی: {format_price(previous)} ریال\n"
        f"{change_text(change)}"
    )


# =========================================================
# BUILD TELEGRAM MESSAGE
# =========================================================

def build_message():

    tgju = get_tgju_prices()

    crypto = get_crypto_prices()

    fear = get_fear_greed()

    money_flow = get_tsetmc_money_flow()

    now = datetime.now(
        TEHRAN_TZ
    ).strftime(
        "%Y/%m/%d - %H:%M"
    )

    bitcoin = crypto["bitcoin"]
    ethereum = crypto["ethereum"]

    fear_value = fear["value"]
    fear_classification = fear["classification"]

    message = f"""
📊 <b>MIRZA</b>
━━━━━━━━━━━━━━━━━━

🏦 <b>بازار ایران</b>

{market_item(
    "طلای ۱۸ عیار",
    "🟡",
    tgju["gold"]
)}

{market_item(
    "سکه امامی",
    "🪙",
    tgju["coin"]
)}

{market_item(
    "دلار",
    "💵",
    tgju["dollar"]
)}

{market_item(
    "یورو",
    "💶",
    tgju["euro"]
)}

━━━━━━━━━━━━━━━━━━

🌐 <b>رمزارزها</b>

₿ <b>بیت‌کوین</b>
💰 ${bitcoin["price"]:,.2f}
{change_text(bitcoin["change"])}

Ξ <b>اتریوم</b>
💰 ${ethereum["price"]:,.2f}
{change_text(ethereum["change"])}

━━━━━━━━━━━━━━━━━━

{money_flow_message(money_flow)}

━━━━━━━━━━━━━━━━━━

{fear_emoji(fear_value)}
<b>شاخص ترس و طمع</b>

🎯 <b>{fear_value}</b> — {fear_classification}

━━━━━━━━━━━━━━━━━━

🕒 <b>آخرین بروزرسانی:</b>
{now}
"""

    return message.strip()


# =========================================================
# SEND TELEGRAM
# =========================================================

def send_telegram(message):

    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN تنظیم نشده است"
        )

    if not CHAT_ID:
        raise ValueError(
            "CHAT_ID تنظیم نشده است"
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    response = session.post(
        url,
        json=payload,
        timeout=20
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return {
        "status": "online",
        "bot": "Mirza",
        "message": "Mirza Bot is running!"
    }


# =========================================================
# SEND
# =========================================================

@app.route("/send")
def send():

    try:

        message = build_message()

        result = send_telegram(
            message
        )

        return {
            "status": "success",
            "message": "Message sent",
            "telegram": result
        }

    except Exception as e:

        return {
            "status": "error",
            "error": str(e)
        }, 500


# =========================================================
# PRICES
# =========================================================

@app.route("/prices")
def prices():

    try:

        return {
            "status": "success",
            "tgju": get_tgju_prices(),
            "crypto": get_crypto_prices(),
            "fear_greed": get_fear_greed(),
            "money_flow": get_tsetmc_money_flow()
        }

    except Exception as e:

        return {
            "status": "error",
            "error": str(e)
        }, 500


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
