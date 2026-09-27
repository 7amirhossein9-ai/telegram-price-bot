import os
import re
import sys
import time
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
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    # tgju sometimes serves a stripped-down page to requests that don't
    # look like a normal browser visit (no Accept-Language / Referer).
    # These extra headers make us look more like a real visit and reduce
    # the chance of getting a page without the price widgets on it.
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.tgju.org/",
}

TEHRAN = ZoneInfo("Asia/Tehran")

# How many times to retry a failed HTTP request before giving up on that
# one asset (with a short backoff between attempts).
HTTP_RETRIES = 3
HTTP_BACKOFF_SECONDS = 2


def log_warning(message):
    """Print diagnostics to stderr so they show up in cron / Actions logs
    without polluting the Telegram message itself."""
    print(f"[WARN] {message}", file=sys.stderr)


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
    """Fetch a tgju page with a few retries. Returns a BeautifulSoup
    object, or raises the last exception if every attempt failed."""

    last_exc = None

    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            response = requests.get(
                url,
                headers=TGJU_HEADERS,
                timeout=20
            )

            response.raise_for_status()

            return BeautifulSoup(response.text, "html.parser")

        except requests.RequestException as exc:
            last_exc = exc
            log_warning(
                f"attempt {attempt}/{HTTP_RETRIES} failed for {url}: {exc}"
            )
            if attempt < HTTP_RETRIES:
                time.sleep(HTTP_BACKOFF_SECONDS * attempt)

    raise last_exc


def _extract_current_price(soup, text):
    """Try several strategies to find the 'current price' value.

    tgju has changed / varies its markup over time, so instead of relying
    on one exact phrase we try a structured lookup first (label cell +
    value cell) and fall back to a handful of regex patterns on the flat
    page text.
    """

    price_labels = ["نرخ فعلی", "قیمت لحظه‌ای", "آخرین قیمت", "آخرین نرخ"]

    # Strategy 1: structured "label then value" elements (table rows,
    # list items, or label/value div pairs all use this same shape).
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

    # Strategy 2: regex over the flattened page text.
    patterns = [
        r"نرخ فعلی\s*[:：]?\s*([\d,٬۰-۹٠-٩]+(?:\.\d+)?)",
        r"قیمت لحظه‌ای\s*[:：]?\s*([\d,٬۰-۹٠-٩]+(?:\.\d+)?)",
        r"آخرین قیمت\s*[:：]?\s*([\d,٬۰-۹٠-٩]+(?:\.\d+)?)",
        r"آخرین نرخ\s*[:：]?\s*([\d,٬۰-۹٠-٩]+(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = clean_number(match.group(1))
            if candidate:
                return candidate

    return None


def _extract_percent_change(soup, text):
    """Try several strategies to find the daily percent change, including
    its direction (up/down).

    Important: tgju frequently renders the change value *unsigned* and
    encodes the direction (up/down) in a CSS class such as "high" / "low"
    on the element instead of a +/- sign in the text. A plain regex over
    the page text misses the sign entirely in that case, which is a very
    likely cause of "the percentages don't work".
    """

    # Strategy 1: an element whose class marks the direction explicitly.
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

    # Strategy 2: regex over the flattened page text, several phrasings,
    # sign optional (tgju sometimes includes it, sometimes not).
    patterns = [
        r"درصد تغییر نسبت به نرخ روز گذشته\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*%",
        r"درصد تغییر نسبت به روز گذشته\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*%",
        r"درصد تغییر\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*%",
        r"تغییر\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*%",
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
            f"(page length: {len(text)} chars) -- tgju may have changed "
            f"its page layout, or served a reduced page to this request"
        )

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

    try:
        response = requests.get(
            url,
            params=params,
            timeout=20
        )

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

    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        log_warning(f"fear & greed fetch failed: {exc}")
        return {"value": None, "classification": None}


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
        "text": message,
        # This was missing before: without it, Telegram shows the <b> and
        # <i> tags in the message as literal text instead of rendering
        # them as bold / italic.
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
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
<b>{fear_greed["value"] if fear_greed["value"] is not None else "-"}</b> — {fear_greed["classification"] or "-"}

🕐 {now.strftime("%H:%M")}

📌 <i>Sources: TGJU | Alternative.me</i>
"""

    send_telegram(message.strip())


if __name__ == "__main__":
    main()
