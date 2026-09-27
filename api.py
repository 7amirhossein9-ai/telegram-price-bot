import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# Optional: set this in Vercel's Environment Variables and pass the same
# value as ?token=... when configuring the Cron Job. This stops random
# people from hitting your public function URL and spamming your channel.
# Leave it unset to disable the check.
CRON_SECRET = os.environ.get("CRON_SECRET")

TGJU_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.tgju.org/",
}

TEHRAN = ZoneInfo("Asia/Tehran")

HTTP_RETRIES = 3
HTTP_BACKOFF_SECONDS = 2


def log_warning(message):
    print(f"[WARN] {message}", file=sys.stderr)


# =========================
# HELPERS
# =========================

def clean_number(value):
    if not value:
        return None

    value = str(value)

    translation = str.maketrans(
        "Û°Û±Û²Û³Û´ÛµÛ¶Û·Û¸Û¹Ù Ù¡Ù¢Ù£Ù¤Ù¥Ù¦Ù§Ù¨Ù©",
        "01234567890123456789"
    )

    value = value.translate(translation)
    value = value.replace(",", "")
    value = value.replace("Ù¬", "")
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
        return "â€”"

    if abs(value) < 0.005:
        return "0.00%"

    if value > 0:
        return f"ðŸŸ¢ +{value:.2f}%"

    return f"ðŸ”´ {value:.2f}%"


# =========================
# TGJU
# =========================

def get_tgju_page(url):
    last_exc = None

    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            response = requests.get(url, headers=TGJU_HEADERS, timeout=20)
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")

        except requests.RequestException as exc:
            last_exc = exc
            log_warning(f"attempt {attempt}/{HTTP_RETRIES} failed for {url}: {exc}")
            if attempt < HTTP_RETRIES:
                time.sleep(HTTP_BACKOFF_SECONDS * attempt)

    raise last_exc


def _extract_current_price(soup, text):
    price_labels = ["Ù†Ø±Ø® ÙØ¹Ù„ÛŒ", "Ù‚ÛŒÙ…Øª Ù„Ø­Ø¸Ù‡â€ŒØ§ÛŒ", "Ø¢Ø®Ø±ÛŒÙ† Ù‚ÛŒÙ…Øª", "Ø¢Ø®Ø±ÛŒÙ† Ù†Ø±Ø®"]

    for label_el in soup.find_all(["th", "td", "span", "div", "li"]):
        label_text = label_el.get_text(" ", strip=True)

        if not label_text or len(label_text) > 40:
            continue

        if any(label_text.startswith(lbl) for lbl in price_labels):
            value_el = label_el.find_next(["td", "span", "div"])
            if value_el:
                candidate = clean_number(value_el.get_text(" ", strip=True))
                if candidate:
                    return candidate

    patterns = [
        r"Ù†Ø±Ø® ÙØ¹Ù„ÛŒ\s*[:ï¼š]?\s*([\d,Ù¬Û°-Û¹Ù -Ù©]+(?:\.\d+)?)",
        r"Ù‚ÛŒÙ…Øª Ù„Ø­Ø¸Ù‡â€ŒØ§ÛŒ\s*[:ï¼š]?\s*([\d,Ù¬Û°-Û¹Ù -Ù©]+(?:\.\d+)?)",
        r"Ø¢Ø®Ø±ÛŒÙ† Ù‚ÛŒÙ…Øª\s*[:ï¼š]?\s*([\d,Ù¬Û°-Û¹Ù -Ù©]+(?:\.\d+)?)",
        r"Ø¢Ø®Ø±ÛŒÙ† Ù†Ø±Ø®\s*[:ï¼š]?\s*([\d,Ù¬Û°-Û¹Ù -Ù©]+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = clean_number(match.group(1))
            if candidate:
                return candidate

    return None


def _extract_percent_change(soup, text):
    for el in soup.find_all(class_=True):
        classes = el.get("class", [])
        if "high" not in classes and "low" not in classes:
            continue

        el_text = el.get_text(" ", strip=True)
        num_match = re.search(r"(\d+(?:\.\d+)?)\s*%", el_text)
        if not num_match:
            continue

        value = float(num_match.group(1))
        return value if "high" in classes else -value

    patterns = [
        r"Ø¯Ø±ØµØ¯ ØªØºÛŒÛŒØ± Ù†Ø³Ø¨Øª Ø¨Ù‡ Ù†Ø±Ø® Ø±ÙˆØ² Ú¯Ø°Ø´ØªÙ‡\s*[:ï¼š]?\s*([+-]?\d+(?:\.\d+)?)\s*%",
        r"Ø¯Ø±ØµØ¯ ØªØºÛŒÛŒØ± Ù†Ø³Ø¨Øª Ø¨Ù‡ Ø±ÙˆØ² Ú¯Ø°Ø´ØªÙ‡\s*[:ï¼š]?\s*([+-]?\d+(?:\.\d+)?)\s*%",
        r"Ø¯Ø±ØµØ¯ ØªØºÛŒÛŒØ±\s*[:ï¼š]?\s*([+-]?\d+(?:\.\d+)?)\s*%",
        r"ØªØºÛŒÛŒØ±\s*[:ï¼š]?\s*([+-]?\d+(?:\.\d+)?)\s*%",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))

    return None


def get_tgju_asset(url):
    try:
        soup = get_tgju_page(url)
    except requests.RequestException as exc:
        log_warning(f"could not fetch {url}: {exc}")
        return None, None

    text = soup.get_text(" ", strip=True)

    current = _extract_current_price(soup, text)
    percent = _extract_percent_change(soup, text)

    if current is None or percent is None:
        missing = []
        if current is None:
            missing.append("price")
        if percent is None:
            missing.append("percent")
        log_warning(
            f"could not read {', '.join(missing)} from {url} "
            f"(page length: {len(text)} chars)"
        )

    return current, percent


# =========================
# CRYPTO
# =========================

def get_crypto():
    url = "https://api.alternative.me/v2/ticker/"
    params = {"convert": "USD", "structure": "array"}

    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()["data"]
    except (requests.RequestException, ValueError, KeyError) as exc:
        log_warning(f"crypto fetch failed: {exc}")
        return {}

    result = {}

    for coin in data:
        slug = coin.get("website_slug")
        if slug not in ["bitcoin", "ethereum"]:
            continue

        try:
            usd = coin["quotes"]["USD"]
            result[slug] = {
                "price": usd["price"],
                "change": usd["percentage_change_24h"]
            }
        except KeyError as exc:
            log_warning(f"unexpected crypto payload shape for {slug}: {exc}")

    return result


# =========================
# FEAR & GREED
# =========================

def get_fear_greed():
    url = "https://api.alternative.me/fng/"

    try:
        response = requests.get(url, params={"limit": 1}, timeout=20)
        response.raise_for_status()
        data = response.json()["data"][0]

        return {
            "value": int(data["value"]),
            "classification": data["value_classification"]
        }

    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        log_warning(f"fear & greed fetch failed: {exc}")
        return {"value": None, "classification": None}


# =========================
# TELEGRAM
# =========================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    response = requests.post(url, data=payload, timeout=20)
    response.raise_for_status()


# =========================
# CORE LOGIC (used by the Flask route below)
# =========================

def run_market_update():
    if not BOT_TOKEN or not CHAT_ID:
        raise ValueError("BOT_TOKEN or CHAT_ID is missing.")

    gold, gold_change = get_tgju_asset("https://www.tgju.org/profile/geram18")
    coin, coin_change = get_tgju_asset("https://www.tgju.org/profile/sekee")
    dollar, dollar_change = get_tgju_asset("https://www.tgju.org/profile/price_dollar_rl")
    yuan, yuan_change = get_tgju_asset("https://www.tgju.org/profile/price_cny")
    index, index_change = get_tgju_asset("https://www.tgju.org/profile/gc30")

    crypto = get_crypto()
    btc = crypto.get("bitcoin")
    eth = crypto.get("ethereum")

    fear_greed = get_fear_greed()

    now = datetime.now(TEHRAN)

    message = f"""
ðŸ“Š <b>MIRZA | MARKET UPDATE</b>

ðŸ‡®ðŸ‡· <b>Ø¨Ø§Ø²Ø§Ø± Ø§ÛŒØ±Ø§Ù†</b>

ðŸ¥‡ Ø·Ù„Ø§ Û±Û¸     <b>{format_price(gold / 10 if gold else None)}</b> ØªÙˆÙ…Ø§Ù†   {format_percent(gold_change)}
ðŸª™ Ø³Ú©Ù‡ Ø§Ù…Ø§Ù…ÛŒ  <b>{format_price(coin / 10 if coin else None)}</b> ØªÙˆÙ…Ø§Ù†   {format_percent(coin_change)}
ðŸ’µ Ø¯Ù„Ø§Ø±       <b>{format_price(dollar / 10 if dollar else None)}</b> ØªÙˆÙ…Ø§Ù†   {format_percent(dollar_change)}
ðŸ‡¨ðŸ‡³ ÛŒÙˆØ§Ù†       <b>{format_price(yuan / 10 if yuan else None)}</b> ØªÙˆÙ…Ø§Ù†   {format_percent(yuan_change)}

ðŸ“ˆ Ø´Ø§Ø®Øµ Ú©Ù„    <b>{format_price(index, 2)}</b>   {format_percent(index_change)}
   Ù†Ø³Ø¨Øª Ø¨Ù‡ Ø±ÙˆØ² Ù‚Ø¨Ù„

â”â”â”â”â”â”â”â”â”â”â”â”

â‚¿ Ø¨ÛŒØªâ€ŒÚ©ÙˆÛŒÙ†    <b>${format_price(btc["price"]) if btc else "-"}</b>   {format_percent(btc["change"] if btc else None)}
Îž Ø§ØªØ±ÛŒÙˆÙ…      <b>${format_price(eth["price"]) if eth else "-"}</b>   {format_percent(eth["change"] if eth else None)}

ðŸ˜¨ <b>Fear & Greed</b>
<b>{fear_greed["value"] if fear_greed["value"] is not None else "-"}</b> â€” {fear_greed["classification"] or "-"}

ðŸ• {now.strftime("%H:%M")}

ðŸ“Œ <i>Sources: TGJU | Alternative.me</i>
"""

    send_telegram(message.strip())

    return {
        "sent": True,
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "gold": gold, "gold_change": gold_change,
        "coin": coin, "coin_change": coin_change,
        "dollar": dollar, "dollar_change": dollar_change,
        "yuan": yuan, "yuan_change": yuan_change,
        "index": index, "index_change": index_change,
        "btc": btc, "eth": eth,
        "fear_greed": fear_greed,
    }


# =========================
# VERCEL / FLASK ENTRYPOINT
# =========================
#
# Vercel's Python runtime looks for a top-level WSGI object named "app"
# (or "application") in this file and calls it for every HTTP request.
# That is what was missing before -- the old script only had
# `if __name__ == "__main__": main()`, which never runs when Vercel
# imports the module to serve a request, so the build failed with
# "Could not find a top-level app, application, or ...".
#
# Configure a Vercel Cron Job (in vercel.json) to hit this route on a
# schedule, e.g. every 15 minutes.

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
@app.route("/api", methods=["GET", "POST"])
def handle_cron():
    if CRON_SECRET:
        supplied = request.args.get("token") or request.headers.get("x-cron-secret")
        if supplied != CRON_SECRET:
            return jsonify({"error": "unauthorized"}), 401

    try:
        result = run_market_update()
        return jsonify(result), 200
    except Exception as exc:
        log_warning(f"run_market_update failed: {exc}")
        return jsonify({"error": str(exc)}), 500


# Local testing: `python api.py` runs a dev server instead of sending
# straight to Telegram, so you can hit http://localhost:5000/ manually.
if __name__ == "__main__":
    app.run(debug=True)
