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

# Optional: set in Vercel Environment Variables and call the endpoint as
# ?token=... (or header x-cron-secret) so random people can't trigger it.
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

YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

TEHRAN = ZoneInfo("Asia/Tehran")

HTTP_RETRIES = 3
HTTP_BACKOFF_SECONDS = 2


def log_warning(message):
    print(f"[WARN] {message}", file=sys.stderr)


# =========================
# GENERIC HELPERS
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


def format_plain_percent(value, decimals=1):
    """For a plain static percentage (e.g. BTC dominance), not a change
    value -- no color, no +/- sign."""
    if value is None:
        return "-"
    return f"{value:.{decimals}f}%"


def format_large_usd(value):
    """1234567890000 -> "$1.23T", 5_600_000_000 -> "$5.60B" """
    if value is None:
        return "-"

    abs_value = abs(value)

    if abs_value >= 1e12:
        return f"${value / 1e12:.2f}T"
    if abs_value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if abs_value >= 1e6:
        return f"${value / 1e6:.2f}M"

    return f"${value:,.0f}"


def http_get_json(url, params=None, headers=None, retries=HTTP_RETRIES):
    last_exc = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            return response.json()

        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            log_warning(f"attempt {attempt}/{retries} failed for {url}: {exc}")
            if attempt < retries:
                time.sleep(HTTP_BACKOFF_SECONDS * attempt)

    log_warning(f"giving up on {url}: {last_exc}")
    return None


# =========================
# TGJU (gold / currencies / Tehran bourse indices)
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
    # tgju frequently encodes direction (up/down) via a CSS class such as
    # "high" / "low" rather than a +/- sign in the text itself.
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
        log_warning(f"could not read {', '.join(missing)} from {url}")

    return current, percent


def get_tgju_asset_multi(candidate_urls):
    """tgju uses slightly different slugs for some instruments than the
    ones documented anywhere, and the exact slug can vary. Try each
    candidate URL in order and return the first one that yields a price.
    """
    for url in candidate_urls:
        price, percent = get_tgju_asset(url)
        if price is not None:
            return price, percent, url

    log_warning(f"all candidate URLs failed: {candidate_urls}")
    return None, None, None


# =========================
# YAHOO FINANCE (oil, silver, DXY)
# =========================

def get_yahoo_quote(symbol):
    """Returns (price, percent_change) for a Yahoo Finance ticker symbol
    (e.g. 'BZ=F' for Brent crude, 'DX-Y.NYB' for the US Dollar Index).
    Percent change is computed vs. the previous close ourselves, since
    that's more reliable than trusting a pre-formatted field.
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    data = http_get_json(url, params={"interval": "1d", "range": "5d"}, headers=YAHOO_HEADERS)

    if not data:
        return None, None

    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")

        if price is None:
            return None, None

        percent = None
        if prev_close:
            percent = (price - prev_close) / prev_close * 100

        return price, percent

    except (KeyError, IndexError, TypeError) as exc:
        log_warning(f"unexpected Yahoo Finance payload for {symbol}: {exc}")
        return None, None


# =========================
# COINGECKO (crypto prices + global stats)
# =========================

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "WLD": "worldcoin-wld",
    "SUI": "sui",
}


def get_crypto_markets():
    """Returns {"BTC": {"price": ..., "change_1h": ..., "change_24h": ...}, ...}"""

    ids = ",".join(COINGECKO_IDS.values())

    data = http_get_json(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "usd",
            "ids": ids,
            "price_change_percentage": "1h,24h",
        },
    )

    if not data:
        return {}

    by_id = {coin["id"]: coin for coin in data}

    result = {}
    for symbol, cg_id in COINGECKO_IDS.items():
        coin = by_id.get(cg_id)
        if not coin:
            continue

        result[symbol] = {
            "price": coin.get("current_price"),
            "change_1h": coin.get("price_change_percentage_1h_in_currency"),
            "change_24h": coin.get("price_change_percentage_24h_in_currency")
                          or coin.get("price_change_percentage_24h"),
        }

    return result


def get_crypto_global():
    """Returns {"btc_dominance": ..., "total_market_cap_usd": ...}"""

    data = http_get_json("https://api.coingecko.com/api/v3/global")

    if not data:
        return {"btc_dominance": None, "total_market_cap_usd": None}

    try:
        market_data = data["data"]
        return {
            "btc_dominance": market_data["market_cap_percentage"].get("btc"),
            "total_market_cap_usd": market_data["total_market_cap"].get("usd"),
        }
    except (KeyError, TypeError) as exc:
        log_warning(f"unexpected CoinGecko /global payload: {exc}")
        return {"btc_dominance": None, "total_market_cap_usd": None}


# =========================
# FEAR & GREED
# =========================

def get_fear_greed():
    data = http_get_json("https://api.alternative.me/fng/", params={"limit": 1})

    if not data:
        return {"value": None, "classification": None}

    try:
        entry = data["data"][0]
        return {
            "value": int(entry["value"]),
            "classification": entry["value_classification"],
        }
    except (KeyError, IndexError, ValueError) as exc:
        log_warning(f"unexpected fear & greed payload: {exc}")
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
# CORE LOGIC
# =========================

def run_market_update():
    if not BOT_TOKEN or not CHAT_ID:
        raise ValueError("BOT_TOKEN or CHAT_ID is missing.")

    # ---- Gold ----
    # geram18 is a confirmed tgju slug. The other two vary by tgju's
    # current layout, so we try a couple of reasonable candidates each.
    gold18, gold18_change, _ = get_tgju_asset_multi(
        ["https://www.tgju.org/profile/geram18"]
    )
    gold_melted, gold_melted_change, _ = get_tgju_asset_multi([
        "https://www.tgju.org/profile/abshodeh",
        "https://www.tgju.org/profile/geram24",
    ])
    gold_ounce, gold_ounce_change, _ = get_tgju_asset_multi([
        "https://www.tgju.org/profile/ons",
        "https://www.tgju.org/profile/ons18",
    ])

    # ---- Currencies ----
    usd, usd_change, _ = get_tgju_asset_multi(
        ["https://www.tgju.org/profile/price_dollar_rl"]
    )
    eur, eur_change, _ = get_tgju_asset_multi(
        ["https://www.tgju.org/profile/price_eur"]
    )
    usdt, usdt_change, _ = get_tgju_asset_multi([
        "https://www.tgju.org/profile/crypto-tether-irr",
        "https://www.tgju.org/profile/price_usdt",
    ])

    # ---- Tehran bourse indices ----
    tse_index, tse_index_change, _ = get_tgju_asset_multi([
        "https://www.tgju.org/profile/gc30",
        "https://www.tgju.org/profile/bourse",
    ])
    tse_hamvazn, tse_hamvazn_change, _ = get_tgju_asset_multi([
        "https://www.tgju.org/profile/bourse-hamvazn",
        "https://www.tgju.org/profile/shakhes-hamvazn",
    ])
    # NOTE: trade value and real-money in/outflow are not included here --
    # see the message at the bottom of the chat reply for why.
    tse_trade_value = None
    tse_real_money_flow = None

    # ---- Crypto ----
    crypto = get_crypto_markets()
    crypto_global = get_crypto_global()
    fear_greed = get_fear_greed()

    # ---- Commodities / global indices ----
    brent_price, brent_change = get_yahoo_quote("BZ=F")
    wti_price, wti_change = get_yahoo_quote("CL=F")
    silver_price, silver_change = get_yahoo_quote("SI=F")
    dxy_price, dxy_change = get_yahoo_quote("DX-Y.NYB")

    # -------------------------
    # Format
    # -------------------------

    now = datetime.now(TEHRAN)

    def crypto_line(symbol, label):
        c = crypto.get(symbol)
        if not c or c.get("price") is None:
            return f"{label}    <b>-</b>"
        return (
            f"{label}    <b>${format_price(c['price'], 2 if c['price'] < 10 else 0)}</b>\n"
            f"      1h: {format_percent(c.get('change_1h'))}   "
            f"24h: {format_percent(c.get('change_24h'))}"
        )

    message = f"""
ðŸ“Š <b>MIRZA | MARKET UPDATE</b>

ðŸ¥‡ <b>Ø·Ù„Ø§</b>
Ø·Ù„Ø§ÛŒ Û±Û¸ Ø¹ÛŒØ§Ø±     <b>{format_price(gold18 / 10 if gold18 else None)}</b> ØªÙˆÙ…Ø§Ù†   {format_percent(gold18_change)}
Ø·Ù„Ø§ÛŒ Ø¢Ø¨â€ŒØ´Ø¯Ù‡      <b>{format_price(gold_melted / 10 if gold_melted else None)}</b> ØªÙˆÙ…Ø§Ù†   {format_percent(gold_melted_change)}
Ø§ÙˆÙ†Ø³ Ø¬Ù‡Ø§Ù†ÛŒ       <b>${format_price(gold_ounce, 2)}</b>   {format_percent(gold_ounce_change)}

ðŸ’µ <b>Ø§Ø±Ø²</b>
Ø¯Ù„Ø§Ø± Ø¢Ø²Ø§Ø¯        <b>{format_price(usd / 10 if usd else None)}</b> ØªÙˆÙ…Ø§Ù†   {format_percent(usd_change)}
ÛŒÙˆØ±Ùˆ             <b>{format_price(eur / 10 if eur else None)}</b> ØªÙˆÙ…Ø§Ù†   {format_percent(eur_change)}
ØªØªØ±              <b>{format_price(usdt / 10 if usdt else None)}</b> ØªÙˆÙ…Ø§Ù†   {format_percent(usdt_change)}

â‚¿ <b>Ø§Ø±Ø²Ù‡Ø§ÛŒ Ø¯ÛŒØ¬ÛŒØªØ§Ù„</b>
{crypto_line("BTC", "Ø¨ÛŒØªâ€ŒÚ©ÙˆÛŒÙ†")}
{crypto_line("ETH", "Ø§ØªØ±ÛŒÙˆÙ…")}
{crypto_line("WLD", "ÙˆØ±Ù„Ø¯Ú©ÙˆÛŒÙ†")}
{crypto_line("SUI", "Ø³ÙˆÛŒ")}

ðŸŒ <b>Ø´Ø§Ø®Øµâ€ŒÙ‡Ø§ÛŒ Ø¬Ù‡Ø§Ù†ÛŒ</b>
BTC Dominance    <b>{format_plain_percent(crypto_global.get("btc_dominance"))}</b>
Market Cap Ú©Ù„    <b>{format_large_usd(crypto_global.get("total_market_cap_usd"))}</b>
Fear & Greed     <b>{fear_greed["value"] if fear_greed["value"] is not None else "-"}</b> â€” {fear_greed["classification"] or "-"}
Ø´Ø§Ø®Øµ Ø¯Ù„Ø§Ø± (DXY)  <b>{format_price(dxy_price, 2)}</b>   {format_percent(dxy_change)}

ðŸ›¢ <b>Ù†ÙØª Ùˆ Ú©Ø§Ù„Ø§</b>
Ù†ÙØª Ø¨Ø±Ù†Øª         <b>${format_price(brent_price, 2)}</b>   {format_percent(brent_change)}
Ù†ÙØª WTI          <b>${format_price(wti_price, 2)}</b>   {format_percent(wti_change)}
Ù†Ù‚Ø±Ù‡             <b>${format_price(silver_price, 2)}</b>   {format_percent(silver_change)}

ðŸ“ˆ <b>Ø¨ÙˆØ±Ø³ Ø§ÛŒØ±Ø§Ù†</b>
Ø´Ø§Ø®Øµ Ú©Ù„          <b>{format_price(tse_index, 2)}</b>   {format_percent(tse_index_change)}
Ø´Ø§Ø®Øµ Ù‡Ù…â€ŒÙˆØ²Ù†       <b>{format_price(tse_hamvazn, 2)}</b>   {format_percent(tse_hamvazn_change)}
Ø§Ø±Ø²Ø´ Ù…Ø¹Ø§Ù…Ù„Ø§Øª      <b>{format_price(tse_trade_value)}</b>
ÙˆØ±ÙˆØ¯/Ø®Ø±ÙˆØ¬ Ù¾ÙˆÙ„ Ø­Ù‚ÛŒÙ‚ÛŒ <b>{format_price(tse_real_money_flow)}</b>

ðŸ• {now.strftime("%H:%M")} â€” {now.strftime("%Y-%m-%d")}

ðŸ“Œ <i>Sources: TGJU | CoinGecko | Yahoo Finance | Alternative.me</i>
"""

    send_telegram(message.strip())

    return {"sent": True, "time": now.strftime("%Y-%m-%d %H:%M:%S")}


# =========================
# VERCEL / FLASK ENTRYPOINT
# =========================

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


if __name__ == "__main__":
    app.run(debug=True)
