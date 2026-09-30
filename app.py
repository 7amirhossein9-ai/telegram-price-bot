import os
import re
import sys
import time
import requests

from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
CRON_SECRET = os.environ.get("CRON_SECRET")

TEHRAN = ZoneInfo("Asia/Tehran")

HTTP_RETRIES = 3
HTTP_BACKOFF_SECONDS = 2


# =========================================================
# HEADERS
# =========================================================

TGJU_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
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


# =========================================================
# LOG
# =========================================================

def log_warning(message):
    print(
        f"[WARN] {message}",
        file=sys.stderr
    )


# =========================================================
# NUMBER HELPERS
# =========================================================

def clean_number(value):

    if value is None:
        return None

    value = str(value)

    translation = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    value = value.translate(
        translation
    )

    value = value.replace(
        ",",
        ""
    )

    value = value.replace(
        "٬",
        ""
    )

    value = value.replace(
        " ",
        ""
    )

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        value
    )

    if not match:
        return None

    try:
        return float(
            match.group()
        )

    except ValueError:
        return None


def format_price(
    value,
    decimals=0
):

    if value is None:
        return "—"

    if decimals == 0:

        return f"{value:,.0f}"

    return f"{value:,.{decimals}f}"


# =========================================================
# PERCENT FORMAT
# =========================================================

def format_percent(value):

    if value is None:
        return "⚪ —"

    try:
        value = float(value)
    except:
        return "⚪ —"

    if abs(value) < 0.005:

        return "⚪ 0.00%"

    if value > 0:

        return f"🟢 +{value:.2f}%"

    return f"🔴 {value:.2f}%"


# =========================================================
# RTL / LTR CONTROL
# =========================================================

RLM = "\u200f"
LRM = "\u200e"


def rtl(text):
    """
    Forces Persian/English labels to behave better
    inside Telegram monospace blocks.
    """

    return f"{RLM}{text}{RLM}"


def ltr(text):
    """
    Keeps numbers and percentages left-to-right.
    """

    return f"{LRM}{text}{LRM}"


# =========================================================
# MARKET ROW
# =========================================================

def market_row(
    label,
    value,
    percent=None,
    value_decimals=0,
    unit=""
):

    label_width = 18
    value_width = 16

    label_text = str(label)

    if unit:
        value_text = (
            format_price(
                value,
                value_decimals
            )
            + " "
            + unit
        )
    else:

        value_text = format_price(
            value,
            value_decimals
        )

    # Keep all numbers in one fixed column.
    value_text = value_text.rjust(
        value_width
    )

    percent_text = format_percent(
        percent
    )

    label_text = label_text.rjust(
        label_width
    )

    return (
        rtl(label_text)
        + " "
        + ltr(value_text)
        + "  "
        + ltr(percent_text)
    )


# =========================================================
# PLAIN ROW
# =========================================================

def plain_row(
    label,
    value,
    value_width=16
):

    label_width = 18

    if value is None:
        value_text = "—"

    else:
        value_text = str(value)

    label_text = str(label).rjust(
        label_width
    )

    value_text = value_text.rjust(
        value_width
    )

    return (
        rtl(label_text)
        + " "
        + ltr(value_text)
    )


# =========================================================
# LARGE USD
# =========================================================

def format_large_usd(value):

    if value is None:
        return "—"

    value = float(value)

    abs_value = abs(value)

    if abs_value >= 1e12:

        return (
            f"${value / 1e12:.2f}T"
        )

    if abs_value >= 1e9:

        return (
            f"${value / 1e9:.2f}B"
        )

    if abs_value >= 1e6:

        return (
            f"${value / 1e6:.2f}M"
        )

    return f"${value:,.0f}"


# =========================================================
# PLAIN PERCENT
# =========================================================

def format_plain_percent(
    value,
    decimals=1
):

    if value is None:
        return "—"

    return (
        f"{float(value):.{decimals}f}%"
    )


# =========================================================
# HTTP JSON
# =========================================================

def http_get_json(
    url,
    params=None,
    headers=None,
    retries=HTTP_RETRIES
):

    last_exc = None

    for attempt in range(
        1,
        retries + 1
    ):

        try:

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=20
            )

            response.raise_for_status()

            return response.json()

        except (
            requests.RequestException,
            ValueError
        ) as exc:

            last_exc = exc

            log_warning(
                f"attempt {attempt}/{retries} "
                f"failed for {url}: {exc}"
            )

            if attempt < retries:

                time.sleep(
                    HTTP_BACKOFF_SECONDS
                    * attempt
                )

    log_warning(
        f"giving up on {url}: {last_exc}"
    )

    return None


# =========================================================
# TGJU PAGE
# =========================================================

def get_tgju_page(url):

    last_exc = None

    for attempt in range(
        1,
        HTTP_RETRIES + 1
    ):

        try:

            response = requests.get(
                url,
                headers=TGJU_HEADERS,
                timeout=20
            )

            response.raise_for_status()

            return BeautifulSoup(
                response.text,
                "html.parser"
            )

        except requests.RequestException as exc:

            last_exc = exc

            log_warning(
                f"attempt {attempt}/{HTTP_RETRIES} "
                f"failed for {url}: {exc}"
            )

            if attempt < HTTP_RETRIES:

                time.sleep(
                    HTTP_BACKOFF_SECONDS
                    * attempt
                )

    raise last_exc


# =========================================================
# TGJU CURRENT PRICE
# =========================================================

def extract_current_price(
    soup,
    text
):

    labels = [
        "نرخ فعلی",
        "قیمت لحظه‌ای",
        "آخرین قیمت",
        "آخرین نرخ"
    ]

    # -----------------------------------------
    # TABLE / HTML
    # -----------------------------------------

    for element in soup.find_all(
        [
            "th",
            "td",
            "span",
            "div",
            "li"
        ]
    ):

        element_text = element.get_text(
            " ",
            strip=True
        )

        if not element_text:
            continue

        if len(element_text) > 50:
            continue

        if any(
            element_text.startswith(label)
            for label in labels
        ):

            next_element = element.find_next(
                [
                    "td",
                    "span",
                    "div"
                ]
            )

            if next_element:

                number = clean_number(
                    next_element.get_text(
                        " ",
                        strip=True
                    )
                )

                if number is not None:

                    return number

    # -----------------------------------------
    # REGEX
    # -----------------------------------------

    patterns = [

        r"نرخ فعلی\s*[:：]?\s*"
        r"([\d,٬۰-۹٠-٩]+(?:\.\d+)?)",

        r"قیمت لحظه‌ای\s*[:：]?\s*"
        r"([\d,٬۰-۹٠-٩]+(?:\.\d+)?)",

        r"آخرین قیمت\s*[:：]?\s*"
        r"([\d,٬۰-۹٠-٩]+(?:\.\d+)?)",

        r"آخرین نرخ\s*[:：]?\s*"
        r"([\d,٬۰-۹٠-٩]+(?:\.\d+)?)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            number = clean_number(
                match.group(1)
            )

            if number is not None:

                return number

    return None


# =========================================================
# TGJU PERCENT
# =========================================================

def extract_percent_change(
    soup,
    text
):

    # -----------------------------------------
    # CSS classes
    # -----------------------------------------

    for element in soup.find_all(
        class_=True
    ):

        classes = element.get(
            "class",
            []
        )

        if (
            "high" not in classes
            and
            "low" not in classes
        ):

            continue

        element_text = element.get_text(
            " ",
            strip=True
        )

        match = re.search(
            r"(\d+(?:\.\d+)?)\s*%",
            element_text
        )

        if not match:
            continue

        value = float(
            match.group(1)
        )

        if "high" in classes:

            return value

        return -value

    # -----------------------------------------
    # Text patterns
    # -----------------------------------------

    patterns = [

        r"درصد تغییر نسبت به نرخ روز گذشته"
        r"\s*[:：]?\s*"
        r"([+-]?\d+(?:\.\d+)?)\s*%",

        r"درصد تغییر نسبت به روز گذشته"
        r"\s*[:：]?\s*"
        r"([+-]?\d+(?:\.\d+)?)\s*%",

        r"درصد تغییر"
        r"\s*[:：]?\s*"
        r"([+-]?\d+(?:\.\d+)?)\s*%",

        r"تغییر"
        r"\s*[:：]?\s*"
        r"([+-]?\d+(?:\.\d+)?)\s*%",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            return float(
                match.group(1)
            )

    return None


# =========================================================
# TGJU ASSET
# =========================================================

def get_tgju_asset(url):

    try:

        soup = get_tgju_page(
            url
        )

    except requests.RequestException as exc:

        log_warning(
            f"could not fetch {url}: {exc}"
        )

        return None, None

    text = soup.get_text(
        " ",
        strip=True
    )

    current = extract_current_price(
        soup,
        text
    )

    percent = extract_percent_change(
        soup,
        text
    )

    if current is None:

        log_warning(
            f"price not found: {url}"
        )

    if percent is None:

        log_warning(
            f"percent not found: {url}"
        )

    return current, percent


# =========================================================
# MULTIPLE TGJU URLS
# =========================================================

def get_tgju_asset_multi(
    urls
):

    for url in urls:

        price, percent = get_tgju_asset(
            url
        )

        if price is not None:

            return (
                price,
                percent,
                url
            )

    return (
        None,
        None,
        None
    )


# =========================================================
# YAHOO FINANCE
# =========================================================

def get_yahoo_quote(
    symbol
):

    url = (
        "https://query1.finance.yahoo.com/"
        f"v8/finance/chart/{symbol}"
    )

    data = http_get_json(
        url,
        params={
            "interval": "1d",
            "range": "5d"
        },
        headers=YAHOO_HEADERS
    )

    if not data:
        return None, None

    try:

        result = data[
            "chart"
        ][
            "result"
        ][0]

        meta = result[
            "meta"
        ]

        price = meta.get(
            "regularMarketPrice"
        )

        previous_close = (
            meta.get("previousClose")
            or
            meta.get("chartPreviousClose")
        )

        if price is None:

            return None, None

        percent = None

        if previous_close:

            percent = (
                (price - previous_close)
                /
                previous_close
                * 100
            )

        return (
            price,
            percent
        )

    except (
        KeyError,
        IndexError,
        TypeError
    ) as exc:

        log_warning(
            f"Yahoo error {symbol}: {exc}"
        )

        return None, None


# =========================================================
# COINGECKO
# =========================================================

COINGECKO_IDS = {

    "BTC":
        "bitcoin",

    "ETH":
        "ethereum",

    "WLD":
        "worldcoin-wld",

    "SUI":
        "sui",
}


def get_crypto_markets():

    ids = ",".join(
        COINGECKO_IDS.values()
    )

    data = http_get_json(

        "https://api.coingecko.com/"
        "api/v3/coins/markets",

        params={

            "vs_currency":
                "usd",

            "ids":
                ids,

            "price_change_percentage":
                "1h,24h",
        }
    )

    if not data:

        return {}

    by_id = {
        coin["id"]: coin
        for coin in data
    }

    result = {}

    for symbol, coin_id in (
        COINGECKO_IDS.items()
    ):

        coin = by_id.get(
            coin_id
        )

        if not coin:
            continue

        result[symbol] = {

            "price":
                coin.get(
                    "current_price"
                ),

            "change_1h":
                coin.get(
                    "price_change_percentage_1h_in_currency"
                ),

            "change_24h":
                coin.get(
                    "price_change_percentage_24h_in_currency"
                )
                or
                coin.get(
                    "price_change_percentage_24h"
                ),
        }

    return result


# =========================================================
# COINGECKO GLOBAL
# =========================================================

def get_crypto_global():

    data = http_get_json(
        "https://api.coingecko.com/"
        "api/v3/global"
    )

    if not data:

        return {
            "btc_dominance":
                None,

            "total_market_cap_usd":
                None,
        }

    try:

        market_data = data[
            "data"
        ]

        return {

            "btc_dominance":
                market_data[
                    "market_cap_percentage"
                ].get("btc"),

            "total_market_cap_usd":
                market_data[
                    "total_market_cap"
                ].get("usd"),
        }

    except (
        KeyError,
        TypeError
    ) as exc:

        log_warning(
            f"CoinGecko global error: {exc}"
        )

        return {
            "btc_dominance":
                None,

            "total_market_cap_usd":
                None,
        }


# =========================================================
# FEAR & GREED
# =========================================================

def get_fear_greed():

    data = http_get_json(
        "https://api.alternative.me/fng/",
        params={
            "limit": 1
        }
    )

    if not data:

        return {
            "value":
                None,

            "classification":
                None,
        }

    try:

        entry = data[
            "data"
        ][0]

        return {

            "value":
                int(
                    entry["value"]
                ),

            "classification":
                entry[
                    "value_classification"
                ],
        }

    except (
        KeyError,
        IndexError,
        ValueError
    ) as exc:

        log_warning(
            f"Fear & Greed error: {exc}"
        )

        return {
            "value":
                None,

            "classification":
                None,
        }


# =========================================================
# CRYPTO ROW
# =========================================================

def crypto_row(
    symbol,
    label,
    crypto
):

    coin = crypto.get(
        symbol
    )

    if not coin:

        return (
            rtl(label.rjust(14))
            + " "
            + ltr("—")
        )

    price = coin.get(
        "price"
    )

    change_1h = coin.get(
        "change_1h"
    )

    change_24h = coin.get(
        "change_24h"
    )

    if price is None:

        price_text = "—"

    elif price < 1:

        price_text = (
            f"${price:.2f}"
        )

    elif price < 10:

        price_text = (
            f"${price:.2f}"
        )

    else:

        price_text = (
            f"${price:,.0f}"
        )

    value_text = price_text.rjust(
        13
    )

    return (
        rtl(label.rjust(14))
        + " "
        + ltr(value_text)
        + "\n"
        + rtl(" " * 14)
        + " "
        + ltr(
            f"1h {format_percent(change_1h)}"
        )
        + "   "
        + ltr(
            f"24h {format_percent(change_24h)}"
        )
    )


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(
    message
):

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    payload = {

        "chat_id":
            CHAT_ID,

        "text":
            message,

        "parse_mode":
            "HTML",

        "disable_web_page_preview":
            True,
    }

    response = requests.post(

        url,

        json=payload,

        timeout=20
    )

    response.raise_for_status()


# =========================================================
# MAIN MARKET UPDATE
# =========================================================

def run_market_update():

    if not BOT_TOKEN:

        raise ValueError(
            "BOT_TOKEN is missing."
        )

    if not CHAT_ID:

        raise ValueError(
            "CHAT_ID is missing."
        )


    # =====================================================
    # GOLD
    # =====================================================

    gold18, gold18_change, _ = (
        get_tgju_asset_multi(
            [
                "https://www.tgju.org/profile/geram18"
            ]
        )
    )

    melted_gold, melted_change, _ = (
        get_tgju_asset_multi(
            [
                "https://www.tgju.org/profile/abshodeh",
                "https://www.tgju.org/profile/geram24",
            ]
        )
    )

    ounce, ounce_change, _ = (
        get_tgju_asset_multi(
            [
                "https://www.tgju.org/profile/ons",
                "https://www.tgju.org/profile/ons18",
            ]
        )
    )


    # =====================================================
    # CURRENCY
    # =====================================================

    usd, usd_change, _ = (
        get_tgju_asset_multi(
            [
                "https://www.tgju.org/profile/price_dollar_rl"
            ]
        )
    )

    eur, eur_change, _ = (
        get_tgju_asset_multi(
            [
                "https://www.tgju.org/profile/price_eur"
            ]
        )
    )

    usdt, usdt_change, _ = (
        get_tgju_asset_multi(
            [
                "https://www.tgju.org/profile/crypto-tether-irr",
                "https://www.tgju.org/profile/price_usdt",
            ]
        )
    )


    # =====================================================
    # IRAN STOCK MARKET
    # =====================================================

    # Main index
    tse_index, tse_index_change, _ = (
        get_tgju_asset_multi(
            [
                "https://www.tgju.org/profile/gc30"
            ]
        )
    )

    # Equal-weight index
    tse_equal, tse_equal_change, _ = (
        get_tgju_asset_multi(
            [
                "https://www.tgju.org/profile/gc31"
            ]
        )
    )

    # At the moment these two are intentionally left empty.
    # We will connect them to a dedicated reliable market-data
    # source instead of showing potentially wrong numbers.

    trade_value = None

    real_money_flow = None


    # =====================================================
    # CRYPTO
    # =====================================================

    crypto = get_crypto_markets()

    crypto_global = get_crypto_global()

    fear_greed = get_fear_greed()


    # =====================================================
    # GLOBAL MARKETS
    # =====================================================

    brent_price, brent_change = (
        get_yahoo_quote(
            "BZ=F"
        )
    )

    wti_price, wti_change = (
        get_yahoo_quote(
            "CL=F"
        )
    )

    silver_price, silver_change = (
        get_yahoo_quote(
            "SI=F"
        )
    )

    dxy_price, dxy_change = (
        get_yahoo_quote(
            "DX-Y.NYB"
        )
    )


    # =====================================================
    # TIME
    # =====================================================

    now = datetime.now(
        TEHRAN
    )


    # =====================================================
    # MESSAGE
    # =====================================================

    message = f"""
📊 <b>MIRZA | MARKET UPDATE</b>

🥇 <b>طلا</b>
<pre>{market_row(
    "طلای ۱۸ عیار",
    gold18 / 10 if gold18 else None,
    gold18_change,
    0,
    "ت"
)}
{market_row(
    "طلای آب‌شده",
    melted_gold / 10 if melted_gold else None,
    melted_change,
    0,
    "ت"
)}
{market_row(
    "اونس جهانی",
    ounce,
    ounce_change,
    2,
    "$"
)}</pre>

💵 <b>ارز</b>
<pre>{market_row(
    "دلار آزاد",
    usd / 10 if usd else None,
    usd_change,
    0,
    "ت"
)}
{market_row(
    "یورو",
    eur / 10 if eur else None,
    eur_change,
    0,
    "ت"
)}
{market_row(
    "تتر",
    usdt / 10 if usdt else None,
    usdt_change,
    0,
    "ت"
)}</pre>

₿ <b>ارزهای دیجیتال</b>
<pre>{crypto_row(
    "BTC",
    "بیت‌کوین",
    crypto
)}
{crypto_row(
    "ETH",
    "اتریوم",
    crypto
)}
{crypto_row(
    "WLD",
    "ورلدکوین",
    crypto
)}
{crypto_row(
    "SUI",
    "سوی",
    crypto
)}</pre>

🌐 <b>شاخص‌های جهانی</b>
<pre>{plain_row(
    "BTC Dominance",
    format_plain_percent(
        crypto_global.get(
            "btc_dominance"
        )
    )
)}
{plain_row(
    "Market Cap کل",
    format_large_usd(
        crypto_global.get(
            "total_market_cap_usd"
        )
    )
)}
{plain_row(
    "Fear & Greed",
    (
        f"{fear_greed['value']} - "
        f"{fear_greed['classification']}"
        if fear_greed["value"] is not None
        else "—"
    )
)}
{market_row(
    "شاخص دلار DXY",
    dxy_price,
    dxy_change,
    2,
    ""
)}</pre>

🛢 <b>نفت و کالا</b>
<pre>{market_row(
    "نفت برنت",
    brent_price,
    brent_change,
    2,
    "$"
)}
{market_row(
    "نفت WTI",
    wti_price,
    wti_change,
    2,
    "$"
)}
{market_row(
    "نقره",
    silver_price,
    silver_change,
    2,
    "$"
)}</pre>

📈 <b>بورس ایران</b>
<pre>{market_row(
    "شاخص کل",
    tse_index,
    tse_index_change,
    2,
    ""
)}
{market_row(
    "شاخص هم‌وزن",
    tse_equal,
    tse_equal_change,
    2,
    ""
)}
{plain_row(
    "ارزش معاملات",
    (
        format_price(
            trade_value
        )
        + " ت"
        if trade_value is not None
        else "—"
    )
)}
{plain_row(
    "ورود/خروج پول",
    (
        format_price(
            real_money_flow
        )
        + " ت"
        if real_money_flow is not None
        else "—"
    )
)}</pre>

🕐 <b>{now.strftime("%H:%M")}</b> — {now.strftime("%Y-%m-%d")}

📌 <i>Sources: TGJU | CoinGecko | Yahoo Finance | Alternative.me</i>
"""

    send_telegram(
        message.strip()
    )

    return {
        "sent": True,
        "time": now.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    }


# =========================================================
# FLASK
# =========================================================

app = Flask(
    __name__
)


@app.route(
    "/",
    methods=[
        "GET",
        "POST"
    ]
)
@app.route(
    "/api",
    methods=[
        "GET",
        "POST"
    ]
)
def handle_cron():

    if CRON_SECRET:

        supplied = (
            request.args.get(
                "token"
            )
            or
            request.headers.get(
                "x-cron-secret"
            )
        )

        if supplied != CRON_SECRET:

            return jsonify({
                "error":
                    "unauthorized"
            }), 401

    try:

        result = run_market_update()

        return jsonify(
            result
        ), 200

    except Exception as exc:

        log_warning(
            f"run_market_update failed: {exc}"
        )

        return jsonify({
            "error":
                str(exc)
        }), 500


# =========================================================
# DEBUG
# =========================================================

@app.route(
    "/debug-tgju"
)
def debug_tgju():

    url = request.args.get(
        "url",
        "https://www.tgju.org/profile/gc30"
    )

    try:

        soup = get_tgju_page(
            url
        )

        text = soup.get_text(
            " ",
            strip=True
        )

        return jsonify({

            "url":
                url,

            "text_length":
                len(text),

            "contains_price":
                "نرخ فعلی" in text,

            "first_500_chars":
                text[:500],
        })

    except Exception as exc:

        return jsonify({

            "url":
                url,

            "error":
                str(exc)

        }), 500


# =========================================================
# LOCAL RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
