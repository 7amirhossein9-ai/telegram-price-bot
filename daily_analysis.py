import os
import html
import requests
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote


BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

TEHRAN = ZoneInfo("Asia/Tehran")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


ASSETS = [
    {
        "symbol": "BTC-USD",
        "name": "بیت‌کوین",
        "chart_name": "Bitcoin",
        "emoji": "₿",
    },
    {
        "symbol": "ETH-USD",
        "name": "اتریوم",
        "chart_name": "Ethereum",
        "emoji": "◆",
    },
    {
        "symbol": "GC=F",
        "name": "طلای جهانی",
        "chart_name": "Gold",
        "emoji": "🥇",
    },
]


# -------------------------------------------------------
# دریافت داده
# -------------------------------------------------------

def get_yahoo_history(symbol):
    encoded_symbol = quote(symbol, safe="")

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{encoded_symbol}"
    )

    params = {
        "range": "8mo",
        "interval": "1d",
        "includePrePost": "false",
        "events": "div,splits",
    }

    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    result = data["chart"]["result"][0]

    timestamps = result["timestamp"]
    quote_data = result["indicators"]["quote"][0]

    df = pd.DataFrame({
        "Date": pd.to_datetime(timestamps, unit="s"),
        "Open": quote_data["open"],
        "High": quote_data["high"],
        "Low": quote_data["low"],
        "Close": quote_data["close"],
        "Volume": quote_data["volume"],
    })

    df = df.dropna(
        subset=["Open", "High", "Low", "Close"]
    )

    df = df.sort_values("Date").reset_index(drop=True)

    if len(df) < 60:
        raise ValueError(
            f"Not enough data for {symbol}"
        )

    return df


# -------------------------------------------------------
# اندیکاتورها
# -------------------------------------------------------

def calculate_rsi(series, period=14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_indicators(df):
    df = df.copy()

    # EMA
    df["EMA20"] = df["Close"].ewm(
        span=20,
        adjust=False
    ).mean()

    df["EMA50"] = df["Close"].ewm(
        span=50,
        adjust=False
    ).mean()

    # RSI
    df["RSI"] = calculate_rsi(
        df["Close"],
        14
    )

    # MACD
    ema12 = df["Close"].ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = df["Close"].ewm(
        span=26,
        adjust=False
    ).mean()

    df["MACD"] = ema12 - ema26

    df["MACD_SIGNAL"] = df["MACD"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["MACD_HIST"] = (
        df["MACD"] -
        df["MACD_SIGNAL"]
    )

    # ATR
    previous_close = df["Close"].shift(1)

    ranges = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - previous_close).abs(),
            (df["Low"] - previous_close).abs(),
        ],
        axis=1,
    )

    true_range = ranges.max(axis=1)

    df["ATR"] = true_range.rolling(
        14
    ).mean()

    return df


# -------------------------------------------------------
# حمایت و مقاومت
# -------------------------------------------------------

def get_support_resistance(df):
    recent = df.tail(30)

    support = recent["Low"].min()
    resistance = recent["High"].max()

    return float(support), float(resistance)


# -------------------------------------------------------
# تحلیل تکنیکال
# -------------------------------------------------------

def analyze_market(df):
    last = df.iloc[-1]

    close = float(last["Close"])
    ema20 = float(last["EMA20"])
    ema50 = float(last["EMA50"])
    rsi = float(last["RSI"])
    macd = float(last["MACD"])
    macd_signal = float(last["MACD_SIGNAL"])
    atr = float(last["ATR"])

    support, resistance = get_support_resistance(df)

    score = 0

    reasons = []

    # قیمت و EMA20
    if close > ema20:
        score += 1
        reasons.append(
            "قیمت بالاتر از میانگین کوتاه‌مدت است."
        )
    else:
        score -= 1
        reasons.append(
            "قیمت پایین‌تر از میانگین کوتاه‌مدت است."
        )

    # EMA20 و EMA50
    if ema20 > ema50:
        score += 1
        reasons.append(
            "ساختار میانگین‌ها صعودی است."
        )
    else:
        score -= 1
        reasons.append(
            "ساختار میانگین‌ها نزولی است."
        )

    # MACD
    if macd > macd_signal:
        score += 1
        reasons.append(
            "MACD مومنتوم مثبت نشان می‌دهد."
        )
    else:
        score -= 1
        reasons.append(
            "MACD مومنتوم منفی نشان می‌دهد."
        )

    # RSI
    if rsi >= 70:
        reasons.append(
            "RSI وارد محدوده اشباع خرید شده است."
        )
    elif rsi <= 30:
        reasons.append(
            "RSI وارد محدوده اشباع فروش شده است."
        )
    elif rsi >= 55:
        score += 1
        reasons.append(
            "RSI قدرت خریداران را نشان می‌دهد."
        )
    elif rsi <= 45:
        score -= 1
        reasons.append(
            "RSI ضعف مومنتوم را نشان می‌دهد."
        )
    else:
        reasons.append(
            "RSI در محدوده خنثی قرار دارد."
        )

    # مومنتوم ۷ روزه
    if len(df) >= 8:
        old_price = float(
            df.iloc[-8]["Close"]
        )

        momentum = (
            (close - old_price) /
            old_price
        ) * 100

        if momentum > 0:
            score += 1
        elif momentum < 0:
            score -= 1
    else:
        momentum = 0

    # نتیجه
    if score >= 3:
        trend = "🟢 صعودی"
        suggestion = (
            "متمایل به خرید؛ بهتر است ورود "
            "پس از اصلاح یا تثبیت قیمت بررسی شود."
        )

    elif score <= -3:
        trend = "🔴 نزولی"
        suggestion = (
            "متمایل به فروش؛ خرید تا زمانی که "
            "نشانه بازگشت دیده نشود پرریسک است."
        )

    else:
        trend = "🟡 خنثی"
        suggestion = (
            "صبر؛ بازار در حال حاضر سیگنال "
            "تکنیکال قدرتمندی ندارد."
        )

    # نزدیک حمایت
    distance_support = (
        (close - support) /
        close
    ) * 100

    # نزدیک مقاومت
    distance_resistance = (
        (resistance - close) /
        close
    ) * 100

    warning = ""

    if rsi >= 70:
        warning = (
            "⚠️ مومنتوم بالاست و احتمال "
            "اصلاح کوتاه‌مدت وجود دارد."
        )

    elif rsi <= 30:
        warning = (
            "⚠️ بازار در اشباع فروش است و "
            "احتمال واکنش صعودی وجود دارد."
        )

    elif distance_resistance < 2:
        warning = (
            "⚠️ قیمت نزدیک مقاومت مهم قرار دارد."
        )

    elif distance_support < 2:
        warning = (
            "⚠️ قیمت نزدیک حمایت مهم قرار دارد."
        )

    return {
        "price": close,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_signal,
        "atr": atr,
        "support": support,
        "resistance": resistance,
        "momentum": momentum,
        "score": score,
        "trend": trend,
        "suggestion": suggestion,
        "warning": warning,
        "reasons": reasons,
    }


# -------------------------------------------------------
# ساخت نمودار
# -------------------------------------------------------

def create_chart(df, asset, analysis):
    chart_df = df.tail(90).copy()

    fig = plt.figure(
        figsize=(12, 10)
    )

    grid = fig.add_gridspec(
        3,
        1,
        height_ratios=[3, 1, 1.2],
        hspace=0.15,
    )

    # ----------------------------
    # قیمت
    # ----------------------------

    ax1 = fig.add_subplot(grid[0])

    ax1.plot(
        chart_df["Date"],
        chart_df["Close"],
        label="Price",
        linewidth=2,
    )

    ax1.plot(
        chart_df["Date"],
        chart_df["EMA20"],
        label="EMA 20",
        linewidth=1.3,
    )

    ax1.plot(
        chart_df["Date"],
        chart_df["EMA50"],
        label="EMA 50",
        linewidth=1.3,
    )

    ax1.axhline(
        analysis["support"],
        linestyle="--",
        linewidth=1,
        label="Support",
    )

    ax1.axhline(
        analysis["resistance"],
        linestyle="--",
        linewidth=1,
        label="Resistance",
    )

    ax1.set_title(
        f"{asset['chart_name']} - Daily Technical Analysis",
        fontsize=16,
        fontweight="bold",
    )

    ax1.set_ylabel("Price USD")

    ax1.grid(
        alpha=0.25
    )

    ax1.legend(
        loc="upper left"
    )

    # ----------------------------
    # RSI
    # ----------------------------

    ax2 = fig.add_subplot(
        grid[1],
        sharex=ax1
    )

    ax2.plot(
        chart_df["Date"],
        chart_df["RSI"],
        linewidth=1.4,
    )

    ax2.axhline(
        70,
        linestyle="--",
        linewidth=1
    )

    ax2.axhline(
        30,
        linestyle="--",
        linewidth=1
    )

    ax2.axhline(
        50,
        linestyle=":",
        linewidth=1
    )

    ax2.set_ylim(
        0,
        100
    )

    ax2.set_ylabel("RSI")

    ax2.grid(
        alpha=0.25
    )

    # ----------------------------
    # MACD
    # ----------------------------

    ax3 = fig.add_subplot(
        grid[2],
        sharex=ax1
    )

    ax3.plot(
        chart_df["Date"],
        chart_df["MACD"],
        label="MACD",
        linewidth=1.3,
    )

    ax3.plot(
        chart_df["Date"],
        chart_df["MACD_SIGNAL"],
        label="Signal",
        linewidth=1.3,
    )

    ax3.bar(
        chart_df["Date"],
        chart_df["MACD_HIST"],
        alpha=0.45,
    )

    ax3.axhline(
        0,
        linewidth=0.8
    )

    ax3.set_ylabel("MACD")

    ax3.grid(
        alpha=0.25
    )

    ax3.legend(
        loc="upper left"
    )

    fig.autofmt_xdate()

    current_price = analysis["price"]

    fig.text(
        0.5,
        0.015,
        (
            f"Price: ${current_price:,.2f}   |   "
            f"RSI: {analysis['rsi']:.1f}   |   "
            f"Support: ${analysis['support']:,.2f}   |   "
            f"Resistance: ${analysis['resistance']:,.2f}"
        ),
        ha="center",
        fontsize=10,
    )

    filename = (
        asset["symbol"]
        .replace("=", "")
        .replace("-", "_")
        + "_analysis.png"
    )

    plt.savefig(
        filename,
        dpi=160,
        bbox_inches="tight",
    )

    plt.close(fig)

    return filename


# -------------------------------------------------------
# متن تلگرام
# -------------------------------------------------------

def create_caption(asset, analysis):
    now = datetime.now(
        TEHRAN
    ).strftime("%Y/%m/%d")

    reasons = analysis["reasons"][:3]

    reason_text = "\n".join(
        f"• {reason}"
        for reason in reasons
    )

    warning = ""

    if analysis["warning"]:
        warning = (
            f"\n\n{analysis['warning']}"
        )

    caption = f"""
{asset['emoji']} <b>تحلیل روزانه {asset['name']}</b>

💰 قیمت: <b>${analysis['price']:,.2f}</b>

📊 وضعیت بازار:
{analysis['trend']}

RSI: <b>{analysis['rsi']:.1f}</b>
EMA20: <b>${analysis['ema20']:,.2f}</b>
EMA50: <b>${analysis['ema50']:,.2f}</b>

🟢 حمایت:
<b>${analysis['support']:,.2f}</b>

🔴 مقاومت:
<b>${analysis['resistance']:,.2f}</b>

🔍 جمع‌بندی:
{reason_text}

💡 <b>دیدگاه تکنیکال:</b>
{analysis['suggestion']}{warning}

📅 {now}
📌 MIRZA | تحلیل تکنیکال
""".strip()

    return caption


# -------------------------------------------------------
# ارسال عکس تلگرام
# -------------------------------------------------------

def send_photo(filename, caption):
    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN is missing"
        )

    if not CHAT_ID:
        raise ValueError(
            "CHAT_ID is missing"
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendPhoto"
    )

    with open(filename, "rb") as image:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML",
            },
            files={
                "photo": image
            },
            timeout=40,
        )

    if not response.ok:
        print(
            response.status_code,
            response.text
        )

        response.raise_for_status()

    return response.json()


# -------------------------------------------------------
# اجرای تحلیل
# -------------------------------------------------------

def run_asset(asset):
    print(
        f"Analyzing {asset['symbol']}..."
    )

    df = get_yahoo_history(
        asset["symbol"]
    )

    df = calculate_indicators(
        df
    )

    analysis = analyze_market(
        df
    )

    chart_file = create_chart(
        df,
        asset,
        analysis
    )

    caption = create_caption(
        asset,
        analysis
    )

    send_photo(
        chart_file,
        caption
    )

    print(
        f"{asset['name']} sent successfully."
    )

    try:
        os.remove(chart_file)
    except OSError:
        pass


def main():
    errors = []

    for asset in ASSETS:
        try:
            run_asset(asset)

        except Exception as error:
            errors.append(
                f"{asset['name']}: {error}"
            )

            print(
                f"ERROR {asset['name']}:",
                error
            )

    if errors:
        print("\nErrors:")

        for error in errors:
            print(error)

        if len(errors) == len(ASSETS):
            raise RuntimeError(
                "All analyses failed."
            )


if __name__ == "__main__":
    main()
