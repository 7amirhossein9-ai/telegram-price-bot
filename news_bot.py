import os
import re
import html
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# RSS feeds
RSS_FEEDS = {
    "بازار و اقتصاد": "https://www.investing.com/rss/121899.rss",
    "کالا و طلا": "https://www.investing.com/rss/commodities.rss",
    "کریپتو": "https://www.investing.com/rss/302.rss",
}

SENT_FILE = "sent_news.txt"

MAX_NEWS_PER_RUN = 2


def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def load_sent_news():
    if not os.path.exists(SENT_FILE):
        return set()

    with open(SENT_FILE, "r", encoding="utf-8") as file:
        return set(line.strip() for line in file if line.strip())


def save_sent_news(sent):
    with open(SENT_FILE, "w", encoding="utf-8") as file:
        for item in sent:
            file.write(item + "\n")


def get_news(feed_url, category):
    try:
        response = requests.get(
            feed_url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=20
        )

        response.raise_for_status()

        root = ET.fromstring(response.content)

        news = []

        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            description = item.findtext("description", "")
            pub_date = item.findtext("pubDate", "")

            title = clean_text(title)
            description = clean_text(description)

            if not title or not link:
                continue

            news.append({
                "title": title,
                "link": link.strip(),
                "description": description,
                "date": pub_date,
                "category": category
            })

        return news

    except Exception as error:
        print(f"RSS error: {error}")
        return []


def create_analysis(news):
    title = news["title"]
    description = news["description"]

    text = (title + " " + description).lower()

    analysis = ""

    if any(word in text for word in [
        "gold",
        "bullion",
        "gold prices"
    ]):
        analysis = (
            "تحلیل میرزا: این خبر مستقیماً با بازار طلا ارتباط دارد. "
            "برای ارزیابی اثر آن باید مسیر دلار، نرخ بهره و بازده اوراق "
            "خزانه آمریکا نیز در کنار خبر بررسی شود."
        )

    elif any(word in text for word in [
        "bitcoin",
        "ethereum",
        "crypto",
        "cryptocurrency"
    ]):
        analysis = (
            "تحلیل میرزا: این خبر می‌تواند روی بازار رمزارزها اثرگذار باشد. "
            "برای ارزیابی شدت اثر، باید واکنش قیمت، حجم معاملات و وضعیت "
            "روند کلی بازار نیز بررسی شود."
        )

    elif any(word in text for word in [
        "fed",
        "federal reserve",
        "interest rate",
        "inflation"
    ]):
        analysis = (
            "تحلیل میرزا: اخبار مربوط به سیاست پولی آمریکا معمولاً "
            "از عوامل مهم اثرگذار بر دلار، طلا، سهام و رمزارزها هستند. "
            "جهت اثرگذاری به برداشت بازار از مسیر نرخ بهره بستگی دارد."
        )

    elif any(word in text for word in [
        "oil",
        "crude",
        "brent",
        "wti"
    ]):
        analysis = (
            "تحلیل میرزا: این خبر به بازار انرژی مربوط است. "
            "اثر آن می‌تواند از مسیر قیمت نفت، تورم و انتظارات اقتصادی "
            "به سایر بازارهای مالی منتقل شود."
        )

    else:
        analysis = (
            "تحلیل میرزا: اهمیت این خبر باید با توجه به واکنش بازار "
            "و ارتباط آن با نرخ بهره، دلار، تورم و جریان نقدینگی بررسی شود."
        )

    return analysis


def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    response = requests.post(
        url,
        data=data,
        timeout=20
    )

    response.raise_for_status()


def main():

    if not BOT_TOKEN or not CHAT_ID:
        raise Exception(
            "BOT_TOKEN or CHAT_ID is missing."
        )

    sent_news = load_sent_news()

    all_news = []

    for category, feed_url in RSS_FEEDS.items():

        news = get_news(
            feed_url,
            category
        )

        all_news.extend(news)

    # جدیدترین خبرها
    all_news = all_news[:30]

    published_count = 0

    for news in all_news:

        news_id = news["link"]

        if news_id in sent_news:
            continue

        analysis = create_analysis(news)

        message = f"""
<b>📰 خبر جدید بازار</b>

<b>{html.escape(news["title"])}</b>

📌 حوزه:
{html.escape(news["category"])}

━━━━━━━━━━━━━━

{html.escape(news["description"])}

━━━━━━━━━━━━━━

<b>🔎 تحلیل میرزا</b>

{html.escape(analysis)}

━━━━━━━━━━━━━━

🔗 <a href="{html.escape(news["link"])}">مشاهده منبع اصلی</a>

#میرزا #بازار #تحلیل
"""

        try:
            send_to_telegram(message)

            print(
                f"Published: {news['title']}"
            )

            sent_news.add(news_id)

            published_count += 1

            if published_count >= MAX_NEWS_PER_RUN:
                break

        except Exception as error:

            print(
                f"Telegram error: {error}"
            )

    save_sent_news(sent_news)

    print(
        f"Finished. Published: {published_count}"
    )


if __name__ == "__main__":
    main()
