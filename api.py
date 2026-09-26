import logging
import os
import re
import time
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mirza")

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
SEND_SECRET = os.environ.get("SEND_SECRET")
TEHRAN_TZ = ZoneInfo("Asia/Tehran")
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "60"))
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}

for name, val in [("BOT_TOKEN", BOT_TOKEN), ("CHAT_ID", CHAT_ID), ("SEND_SECRET", SEND_SECRET)]:
    if not val:
        logger.warning("%s تنظیم نشده", name)


# ============================== SESSION / CACHE ==============================

def build_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


session = build_session()
_cache = {}


def ttl_cache(ttl):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            key = (fn.__name__, a, tuple(sorted(kw.items())))
            now = time.time()
            if key in _cache and now - _cache[key][1] < ttl:
                return _cache[key][0]
            value = fn(*a, **kw)
            _cache[key] = (value, now)
            return value
        return wrapper
    return deco


# ============================== HELPERS ==============================

def clean_number(value):
    if value is None:
        return None
    value = re.sub(r"[^\d.\-+]", "", str(value).replace(",", "").replace("٬", "").replace("٫", ".").replace("%", ""))
    try:
        return float(value) if value else None
    except ValueError:
        return None


def format_price(value):
    if value is None:
        return "نامشخص"
    return f"{int(value):,}" if float(value).is_integer() else f"{value:,.2f}"


def format_money(value):
    return "نامشخص" if value is None else f"{value / 10 / 1_000_000_000:,.1f} میلیارد"


def calculate_change(current, previous):
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous * 100


def change_text(change):
    if change is None:
        return "⚪ نامشخص"
    if change > 0:
        return f"🟢 +{change:.2f}%"
    if change < 0:
        return f"🔴 {change:.2f}%"
    return "⚪ 0.00%"


def require_secret(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not SEND_SECRET:
            return fn(*a, **kw)
        provided = request.headers.get("X-Secret") or request.args.get("secret")
        if provided != SEND_SECRET:
            return jsonify({"status": "error", "error": "دسترسی غیرمجاز"}), 401
        return fn(*a, **kw)
    return wrapper


# ============================== TGJU (طلا/سکه/ارز/بورس) ==============================

TGJU_PROFILES = {
    "gold": "https://www.tgju.org/profile/geram18",
    "coin": "https://www.tgju.org/profile/sekee",
    "dollar": "https://www.tgju.org/profile/price_dollar_rl",
    "euro": "https://www.tgju.org/profile/price_eur",
    "bourse": "https://www.tgju.org/profile/bourse",  # شاخص کل بورس تهران
}


def get_tgju_current(url):
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
    match = re.search(r"نرخ فعلی\s*::?\s*([\d,]+)", text)
    if not match:
        raise ValueError("قیمت فعلی پیدا نشد")
    return clean_number(match.group(1))


def get_tgju_previous_close(url):
    resp = session.get(url.rstrip("/") + "/history", timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for table in soup.find_all("table"):
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 5:
                continue
            values = [c.get_text(" ", strip=True) for c in cells]
            closing = clean_number(values[3])  # پایانی
            if closing:
                return closing
    return None


@ttl_cache(CACHE_TTL)
def get_tgju_prices():
    result = {}
    for name, url in TGJU_PROFILES.items():
        try:
            current = get_tgju_current(url)
            previous = get_tgju_previous_close(url)
            result[name] = {"current": current, "previous": previous, "change": calculate_change(current, previous)}
        except Exception as e:
            logger.error("TGJU خطا - %s: %s", name, e)
            result[name] = {"current": None, "previous": None, "change": None}
    return result


# ============================== CRYPTO ==============================

@ttl_cache(CACHE_TTL)
def get_crypto_prices():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether&vs_currencies=usd&include_24hr_change=true"
    data = session.get(url, timeout=20).json()
    return {
        coin: {"price": data[coin]["usd"], "change": data[coin].get("usd_24h_change", 0)}
        for coin in ("bitcoin", "ethereum", "tether")
    }


# ============================== FEAR & GREED ==============================

@ttl_cache(CACHE_TTL)
def get_fear_greed():
    data = session.get("https://api.alternative.me/fng/?limit=1", timeout=20).json()["data"][0]
    return {"value": int(data["value"]), "classification": data["value_classification"]}


def fear_emoji(v):
    return "😱" if v <= 24 else "😨" if v <= 44 else "😐" if v <= 55 else "😀" if v <= 74 else "🤑"


# ============================== MESSAGE FORMATTING ==============================

def market_item(title, emoji, data):
    if not data:
        return f"{emoji} {title}\n💰 نامشخص"
    return (
        f"{emoji} {title}\n"
        f"💰 {format_price(data.get('current'))} ریال\n"
        f"📌 قبلی: {format_price(data.get('previous'))} ریال\n"
        f"{change_text(data.get('change'))}"
    )


def build_message():
    tgju = get_tgju_prices()
    crypto = get_crypto_prices()
    fear = get_fear_greed()
    now = datetime.now(TEHRAN_TZ).strftime("%Y/%m/%d - %H:%M")

    btc, eth, usdt = crypto["bitcoin"], crypto["ethereum"], crypto["tether"]

    return f"""
📊 <b>MIRZA</b>
━━━━━━━━━━━━━━━━━━

🏦 <b>بازار ایران</b>

{market_item("طلای ۱۸ عیار", "🟡", tgju["gold"])}

{market_item("سکه امامی", "🪙", tgju["coin"])}

{market_item("دلار", "💵", tgju["dollar"])}

{market_item("یورو", "💶", tgju["euro"])}

📈 <b>شاخص کل بورس</b>
{change_text(tgju["bourse"]["change"])} — {format_price(tgju["bourse"]["current"])} واحد

━━━━━━━━━━━━━━━━━━

🌐 <b>رمزارزها</b>

₿ بیت‌کوین: ${btc['price']:,.2f} {change_text(btc['change'])}
Ξ اتریوم: ${eth['price']:,.2f} {change_text(eth['change'])}
₮ تتر: ${usdt['price']:,.4f} {change_text(usdt['change'])}

━━━━━━━━━━━━━━━━━━

{fear_emoji(fear['value'])} <b>ترس و طمع:</b> {fear['value']} — {fear['classification']}

━━━━━━━━━━━━━━━━━━
🕒 {now}
""".strip()


# ============================== TELEGRAM ==============================

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        raise ValueError("BOT_TOKEN یا CHAT_ID تنظیم نشده است")

    resp = session.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


# ============================== ROUTES ==============================

@app.route("/")
def home():
    return jsonify({"status": "online", "bot": "Mirza"})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now(TEHRAN_TZ).isoformat()})


@app.route("/send")
@require_secret
def send():
    try:
        result = send_telegram(build_message())
        return jsonify({"status": "success", "telegram": result})
    except Exception as e:
        logger.exception("خطا در ارسال پیام")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/prices")
def prices():
    try:
        return jsonify({
            "status": "success",
            "tgju": get_tgju_prices(),
            "crypto": get_crypto_prices(),
            "fear_greed": get_fear_greed(),
        })
    except Exception as e:
        logger.exception("خطا در دریافت قیمت‌ها")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"status": "error", "error": "مسیر پیدا نشد"}), 404


@app.errorhandler(500)
def server_error(_e):
    return jsonify({"status": "error", "error": "خطای داخلی سرور"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
