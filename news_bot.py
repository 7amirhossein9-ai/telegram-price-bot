import os
import re
import html
import requests
import xml.etree.ElementTree as ET

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

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
        return set(
            line.strip()
            for line in file
            if line.strip()
        )


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

        root = ET.fromstring(
            response.content
        )

        news = []

        for item in root.findall(".//item"):

            title = item.findtext(
                "title",
                ""
            )

            link = item.findtext(
                "link",
                ""
            )

            description = item.findtext(
                "description",
                ""
            )

            pub_date = item.findtext(
                "pubDate",
                ""
            )

            title = clean_text(title)
            description = clean_text(
                description
            )

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

        print(
            f"RSS error: {error}"
        )

        return []


def ask_ai(news):

    prompt = f"""
تو یک تحلیلگر بازار مالی برای کانال تلگرامی Mirza هستی.

خبر زیر را بررسی کن.

عنوان:
{news["title"]}

متن خبر:
{news["description"]}

خروجی را فقط به زبان فارسی تولید کن.

خروجی شامل این بخش‌ها باشد:

1. خلاصه خبر
در 2 تا 3 جمله توضیح بده خبر درباره چیست.

2. تحلیل بازار
توضیح بده این خبر ممکن است روی کدام بازارها اثر بگذارد:
طلا، دلار، نفت، بورس یا رمزارزها.

3. جهت احتمالی اثر
اگر شواهد کافی وجود دارد بگو:
مثبت
منفی
خنثی
یا نامشخص

اگر اطلاعات کافی برای تعیین جهت وجود ندارد، صریحاً بگو «نامشخص».

4. نکته مهم
یک نکته کوتاه درباره چیزی که معامله‌گران باید برای ارزیابی اثر واقعی خبر زیر نظر داشته باشند.

هیچ اطلاعاتی را که در خبر وجود ندارد به عنوان واقعیت اضافه نکن.

تحلیل قطعی یا توصیه خرید و فروش ارائه نده.

مختصر و مناسب انتشار در تلگرام بنویس.
"""

    url = "https://api.openai.com/v1/responses"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-5.6-luna",
        "input": prompt
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=60
    )

    response.raise_for_status()

    result = response.json()

    return result["output"][0]["content"][0]["text"]


def send_to_telegram(message):

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

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

    if not BOT_TOKEN:
        raise Exception(
            "BOT_TOKEN is missing."
        )

    if not CHAT_ID:
        raise Exception(
            "CHAT_ID is missing."
        )

    if not OPENAI_API_KEY:
        raise Exception(
            "OPENAI_API_KEY is missing."
        )

    sent_news = load_sent_news()

    all_news = []

    for category, feed_url in RSS_FEEDS.items():

        news = get_news(
            feed_url,
            category
        )

        all_news.extend(news)

    published_count = 0

    for news in all_news:

        news_id = news["link"]

        if news_id in sent_news:
            continue

        try:

            ai_text = ask_ai(news)

            message = f"""
<b>📰 خبر جدید بازار</b>

<b>{html.escape(news["title"])}</b>

📌 حوزه:
{html.escape(news["category"])}

━━━━━━━━━━━━━━

<b>🤖 خلاصه و تحلیل میرزا</b>

{html.escape(ai_text)}

━━━━━━━━━━━━━━

🔗 <a href="{html.escape(news["link"])}">منبع اصلی خبر</a>

#میرزا #بازار #تحلیل
"""

            send_to_telegram(message)

            sent_news.add(news_id)

            published_count += 1

            print(
                f"Published: {news['title']}"
            )

            if published_count >= MAX_NEWS_PER_RUN:
                break

        except Exception as error:

            print(
                f"Processing error: {error}"
            )

    save_sent_news(sent_news)

    print(
        f"Finished. Published: {published_count}"
    )


if __name__ == "__main__":
    main()
