import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

TGJU_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/130 Safari/537.36"
    )
}

TEHRAN = ZoneInfo("Asia/Tehran")


# =========================
# HELPERS
# =========================

def clean_number(value):
    """Convert Persian/Arabic digits and remove separators."""

    if not value:
        return None

    value = str(value)

    translation = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    value = value.translate(translation)

    value = value.replace(",", "")
    value = value.replace("٬", "")
    value = value.replace(" ", "")

    match = re.search(r"-?\d+(?:\.\d+)?", value)

    if not match:
        return None

    return float(match.group())


def format_price(value, decimals=0):
    if value is None:
        return "-"

    if decimals == 0:
        return f"{value:,.0f}"

    return f"{value:,.{decimals}f}"


def format_percent(value):
    if value is None:
        return "—"

    if abs(value) < 0.005:
        return "0.00%"

    if value > 0:
        return f"🟢 +{value:.2f}%"

    return f"🔴 {value:.2f}%"


# =========================
# TGJU
# =========================

def get_tgju_page(url):

    response = requests.get(
        url,
        headers=TGJU_HEADERS,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    return soup


def get_tgju_asset(url):

    soup = get_tgju_page(url)

    text = soup.get_text(" ", strip=True)

    # نرخ فعلی
    current_match = re.search(
        r"نرخ فعلی\s*[:：]+\s*([\d,٬۰-۹٠-٩]+(?:\.\d+)?)",
        text
    )

    current = clean_number(
        current_match.group(1)
    ) if current_match else None

    # درصد تغییر نسبت به روز گذشته
    percent_patterns = [
        r"درصد تغییر نسبت به نرخ روز گذشته\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*%",
        r"درصد تغییر نسبت نرخ روز گذشته\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*%"
    ]

    percent = None

    for pattern in percent_patterns:

        match = re.search(pattern, text)

        if match:
            percent = float(match.group(1))
            break

    return current, percent


# =========================
# CRYPTO
# =========================

def get_crypto():

    url = "https://api.alternative.me/v2/ticker/"

    params = {
        "convert": "USD",
        "structure": "array"
    }

    response = requests.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()["data"]

    result = {}

    for coin in data:

        slug = coin.get("website_slug")

        if slug not in ["bitcoin", "ethereum"]:
            continue

        usd = coin["quotes"]["USD"]

        result[slug] = {
            "price": usd["price"],
            "change": usd["percentage_change_24h"]
        }

    return result


# =========================
# FEAR & GREED
# =========================

def get_fear_greed():

    url = "https://api.alternative.me/fng/"

    response = requests.get(
        url,
        params={"limit": 1},
        timeout=20
    )

    response.raise_for_status()

    data = response.json()["data"][0]

    return {
        "value": int(data["value"]),
        "classification": data["value_classification"]
    }


# =========================
# TELEGRAM
# =========================

def send_telegram(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    response = requests.post(
        url,
        data=payload,
        timeout=20
    )

    response.raise_for_status()


# =========================
# MAIN
# =========================

def main():

    if not BOT_TOKEN or not CHAT_ID:
        raise ValueError(
            "BOT_TOKEN or CHAT_ID is missing."
        )

    # -------------------------
    # Iran Market
    # -------------------------

    gold, gold_change = get_tgju_asset(
        "https://www.tgju.org/profile/geram18"
    )

    coin, coin_change = get_tgju_asset(
        "https://www.tgju.org/profile/sekee"
    )

    dollar, dollar_change = get_tgju_asset(
        "https://www.tgju.org/profile/price_dollar_rl"
    )

    yuan, yuan_change = get_tgju_asset(
        "https://www.tgju.org/profile/price_cny"
    )

    index, index_change = get_tgju_asset(
        "https://www.tgju.org/profile/gc30"
    )

    # -------------------------
    # Crypto
    # -------------------------

    crypto = get_crypto()

    btc = crypto.get("bitcoin")
    eth = crypto.get("ethereum")

    fear_greed = get_fear_greed()

    # -------------------------
    # Format
    # -------------------------

    now = datetime.now(TEHRAN)

    message = f"""
📊 <b>MIRZA | MARKET UPDATE</b>

🇮🇷 <b>بازار ایران</b>

🥇 طلا ۱۸     <b>{format_price(gold / 10 if gold else None)}</b> تومان   {format_percent(gold_change)}
🪙 سکه امامی  <b>{format_price(coin / 10 if coin else None)}</b> تومان   {format_percent(coin_change)}
💵 دلار       <b>{format_price(dollar / 10 if dollar else None)}</b> تومان   {format_percent(dollar_change)}
🇨🇳 یوان       <b>{format_price(yuan / 10 if yuan else None)}</b> تومان   {format_percent(yuan_change)}

📈 شاخص کل    <b>{format_price(index, 2)}</b>   {format_percent(index_change)}
   نسبت به روز قبل

━━━━━━━━━━━━

₿ بیت‌کوین    <b>${format_price(btc["price"]) if btc else "-"}</b>   {format_percent(btc["change"] if btc else None)}
Ξ اتریوم      <b>${format_price(eth["price"]) if eth else "-"}</b>   {format_percent(eth["change"] if eth else None)}

😨 <b>Fear & Greed</b>
<b>{fear_greed["value"]}</b> — {fear_greed["classification"]}

🕐 {now.strftime("%H:%M")}

📌 <i>Sources: TGJU | Alternative.me</i>
"""

    send_telegram(message.strip())


if __name__ == "__main__":
    main()
