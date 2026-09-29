import os
import re
import html
import time
import requests
import xml.etree.ElementTree as ET

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

RSS_FEEDS = {
    "بازار و اقتصاد": "https://www.investing.com/rss/121899.rss",
    "کالا و طلا": "https://www.investing.com/rss/commodities.rss",
    "کریپتو": "https://www.investing.com/rss/302.rss",
}

SENT_FILE = "sent_news.txt"

MAX_NEWS_PER_RUN = 1

GEMINI_MODEL = "gemini-3.5-flash-lite"


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

        root = ET.fromstring(response.content)

        news = []

        for item in root.findall(".//item"):

            title = clean_text(
                item.findtext("title", "")
            )

            link = item.findtext(
                "link",
                ""
            ).strip()

            description = clean_text(
                item.findtext(
                    "description",
                    ""
                )
            )

            if not title or not link:
                continue

            news.append({
                "title": title,
                "link": link,
                "description": description,
                "category": category
            })

        return news

    except Exception as error:

        print(f"RSS error: {error}")

        return []


def ask_gemini(news):

    prompt = f"""
تو تحلیلگر بازار مالی برای کانال تلگرامی Mirza هستی.

خبر زیر را بررسی کن.

عنوان:
{news["title"]}

متن:
{news["description"]}

فقط فارسی بنویس.

ساختار:

📝 خلاصه خبر:
2 تا 3 جمله.

📊 تحلیل بازار:
توضیح بده خبر چه اثری ممکن است روی
طلا، دلار، نفت، بورس یا رمزارزها داشته باشد.

📈 جهت احتمالی اثر:
مثبت / منفی / خنثی / نامشخص

اگر اطلاعات کافی نیست:
نامشخص

🔎 نکته مهم:
یک نکته کوتاه برای پیگیری بازار.

اطلاعاتی که در خبر نیست را به عنوان واقعیت اضافه نکن.

توصیه خرید یا فروش نده.

متن کوتاه و مناسب تلگرام باشد.
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    headers = {
        "Content-Type": "application/json"
    }

    params = {
        "key": GEMINI_API_KEY
    }

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    for attempt in range(3):

        try:

            response = requests.post(
                url,
                headers=headers,
                params=params,
                json=data,
                timeout=60
            )

            if response.status_code == 200:

                result = response.json()

                return (
                    result["candidates"][0]
                    ["content"]["parts"][0]["text"]
                )

            if response.status_code in [429, 503]:

                print(
                    f"Gemini temporary error "
                    f"{response.status_code}. "
                    f"Attempt {attempt + 1}/3"
                )

                if attempt < 2:
                    time.sleep(20)
                    continue

                raise Exception(
                    f"Gemini unavailable: "
                    f"HTTP {response.status_code}"
                )

            print(
                "Gemini response:",
                response.text[:1000]
            )

            response.raise_for_status()

        except requests.exceptions.RequestException as error:

            if attempt == 2:
                raise error

            print(
                f"Connection error. "
                f"Retry {attempt + 1}/3"
            )

            time.sleep(20)

    raise Exception(
        "Gemini request failed."
    )


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

    if not GEMINI_API_KEY:
        raise Exception(
            "GEMINI_API_KEY is missing."
        )

    sent_news = load_sent_news()

    all_news = []

    for category, feed_url in RSS_FEEDS.items():

        news = get_news(
            feed_url,
            category
        )

        all_news.extend(news)

    print(
        f"Total RSS news found: {len(all_news)}"
    )

    for news in all_news:

        news_id = news["link"]

        if news_id in sent_news:
            continue

        print(
            f"New news found: {news['title']}"
        )

        try:

            ai_text = ask_gemini(news)

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

            save_sent_news(sent_news)

            print(
                "Telegram message sent successfully."
            )

            print(
                "Finished. Published: 1"
            )

            return

        except Exception as error:

            print(
                f"Processing stopped: {error}"
            )

            return

    print(
        "Finished. Published: 0"
    )


if __name__ == "__main__":
    main()
