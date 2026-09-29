import os
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# مدل رایگان Gemini
GEMINI_MODEL = "gemini-3.7-flash"

MAX_CANDIDATES = 15

SENT_FILE = "sent_news.txt"


# =========================================================
# NEWS SOURCES
# =========================================================

RSS_FEEDS = {

    "اقتصاد و بازار":
        "https://www.investing.com/rss/121899.rss",

    "کالا و طلا":
        "https://www.investing.com/rss/commodities.rss",

    "کریپتو":
        "https://www.investing.com/rss/302.rss",

}


# =========================================================
# CHECK ENVIRONMENT
# =========================================================

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN is missing")

if not CHAT_ID:
    raise Exception("CHAT_ID is missing")

if not GEMINI_API_KEY:
    raise Exception("GEMINI_API_KEY is missing")


# =========================================================
# SENT NEWS
# =========================================================

def load_sent_news():

    if not os.path.exists(SENT_FILE):
        return set()

    with open(SENT_FILE, "r", encoding="utf-8") as file:

        return set(
            line.strip()
            for line in file
            if line.strip()
        )


def save_sent_news(sent_news):

    with open(SENT_FILE, "w", encoding="utf-8") as file:

        for link in sent_news:
            file.write(link + "\n")


# =========================================================
# RSS READER
# =========================================================

def get_news():

    all_news = []

    for category, url in RSS_FEEDS.items():

        try:

            response = requests.get(
                url,
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            response.raise_for_status()

            root = ET.fromstring(response.content)

            for item in root.findall(".//item"):

                title = item.findtext("title")

                link = item.findtext("link")

                description = item.findtext("description")

                pub_date = item.findtext("pubDate")

                if not title or not link:
                    continue

                all_news.append({

                    "category": category,

                    "title": title.strip(),

                    "link": link.strip(),

                    "description": (
                        description.strip()
                        if description
                        else ""
                    ),

                    "pub_date": (
                        pub_date.strip()
                        if pub_date
                        else ""
                    )

                })

        except Exception as error:

            print(
                f"RSS error [{category}]: {error}"
            )

    return all_news


# =========================================================
# REMOVE DUPLICATES
# =========================================================

def remove_duplicates(news):

    result = []

    seen_links = set()

    seen_titles = set()

    for item in news:

        link = item["link"]

        title = item["title"].lower()

        if link in seen_links:
            continue

        if title in seen_titles:
            continue

        seen_links.add(link)

        seen_titles.add(title)

        result.append(item)

    return result


# =========================================================
# KEYWORD IMPORTANCE
# =========================================================

IMPORTANT_WORDS = [

    # Crypto
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "crypto",
    "cryptocurrency",
    "solana",
    "xrp",

    # Gold
    "gold",
    "silver",
    "bullion",

    # Economy
    "inflation",
    "interest rate",
    "fed",
    "federal reserve",
    "ecb",
    "central bank",
    "recession",
    "gdp",
    "jobs",
    "employment",
    "unemployment",

    # Markets
    "stock",
    "stocks",
    "shares",
    "nasdaq",
    "s&p",
    "dow",
    "market",

    # Commodities
    "oil",
    "crude",
    "opec",

    # Politics / geopolitics
    "trump",
    "tariff",
    "sanction",
    "sanctions",
    "iran",
    "israel",
    "ukraine",
    "russia",
    "china",
    "war",
    "election",

]


def keyword_score(item):

    text = (
        item["title"] +
        " " +
        item["description"]
    ).lower()

    score = 0

    for word in IMPORTANT_WORDS:

        if word in text:

            score += 3

    return score


# =========================================================
# PRE-FILTER NEWS
# =========================================================

def prepare_candidates(news, sent_news):

    candidates = []

    for item in news:

        if item["link"] in sent_news:
            continue

        score = keyword_score(item)

        item["keyword_score"] = score

        candidates.append(item)

    candidates.sort(
        key=lambda x: x["keyword_score"],
        reverse=True
    )

    return candidates[:MAX_CANDIDATES]


# =========================================================
# GEMINI
# =========================================================

def ask_gemini(prompt):

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

        ],

        "generationConfig": {

            "temperature": 0.2,

            "maxOutputTokens": 900

        }

    }

    for attempt in range(3):

        try:

            response = requests.post(
                url,
                params=params,
                headers=headers,
                json=data,
                timeout=60
            )

            if response.status_code in [429, 503]:

                print(
                    f"Gemini temporary error: "
                    f"{response.status_code}"
                )

                if attempt < 2:

                    time.sleep(20)

                    continue

                return None

            response.raise_for_status()

            result = response.json()

            return (
                result["candidates"][0]
                ["content"]["parts"][0]["text"]
            )

        except Exception as error:

            print(
                f"Gemini error: {error}"
            )

            if attempt < 2:

                time.sleep(20)

            else:

                return None

    return None


# =========================================================
# AI NEWS SELECTION + ANALYSIS
# =========================================================

def analyze_news(candidates):

    news_text = ""

    for index, item in enumerate(candidates, start=1):

        news_text += f"""

خبر شماره {index}

دسته:
{item["category"]}

عنوان:
{item["title"]}

توضیح:
{item["description"]}

زمان:
{item["pub_date"]}

لینک:
{item["link"]}

امتیاز اولیه:
{item["keyword_score"]}

--------------------------------
"""


    prompt = f"""
تو سردبیر حرفه‌ای یک کانال فارسی به نام «میرزا» هستی.

وظیفه تو این است که از بین خبرهای زیر فقط
مهم‌ترین خبر اقتصادی/بازاری روز را انتخاب کنی.

موضوعات مهم:

- طلا
- بیت‌کوین
- اتریوم
- رمزارزها
- سهام و بورس
- شرکت‌های بزرگ
- دلار و ارز
- نفت
- تورم
- نرخ بهره
- بانک‌های مرکزی
- اقتصاد جهانی
- سیاست‌هایی که روی اقتصاد و بازار اثر دارند
- جنگ، تحریم، تعرفه و تنش‌های ژئوپلیتیکی با اثر اقتصادی

خبر را با این معیارها بررسی کن:

1. تازگی خبر
2. اهمیت واقعی
3. اثر احتمالی روی بازار
4. میزان توجه بازار به موضوع
5. ارتباط با طلا، کریپتو، سهام، ارز یا اقتصاد
6. تکراری نبودن
7. معتبر بودن منبع

اگر چند خبر مهم هستند، فقط یکی را انتخاب کن.

نکته مهم:

خبرهای صرفاً سرگرمی، تبلیغاتی، کم‌اهمیت،
تحلیل‌های بدون اتفاق جدید و اخبار تکراری را انتخاب نکن.

اگر هیچ خبر واقعاً مهمی وجود ندارد،
دقیقاً بنویس:

NO_IMPORTANT_NEWS


اگر خبر مربوط به یک سهم یا شرکت است:

- اسم شرکت را واضح بنویس.
- اگر نماد سهام در خبر وجود دارد، نماد را هم بنویس.
- توضیح بده خبر چه اثری می‌تواند روی آن شرکت یا صنعت داشته باشد.
- در پایان لینک اصلی خبر را برای اطلاعات بیشتر قرار بده.

اگر خبر مربوط به اتریوم یا بیت‌کوین است:

- توضیح بده چه اتفاقی افتاده.
- چرا برای بازار مهم است.
- اثر احتمالی روی بازار کریپتو را توضیح بده.

اگر خبر مربوط به طلا است:

- توضیح بده چرا طلا تحت تأثیر این خبر قرار گرفته.
- در صورت ارتباط، نرخ بهره، دلار، تورم یا ریسک‌های ژئوپلیتیکی را توضیح بده.

اگر خبر سیاسی است:

فقط اثر اقتصادی و بازاری آن را توضیح بده.
از تبلیغ یا حمایت از هیچ حزب، فرد یا جریان سیاسی خودداری کن.

هیچ توصیه خرید یا فروش نده.

متن نهایی باید فارسی، کوتاه و کاربردی باشد.

حداکثر حدود 250 کلمه.

ساختار خروجی:

🔥 تیتر

📰 چه اتفاقی افتاده؟
یک توضیح کوتاه و واضح.

📊 تحلیل میرزا
توضیح بده این خبر چرا مهم است و چه بازارهایی ممکن است تحت تأثیر قرار بگیرند.

🎯 بازار مرتبط
مثلاً:
طلا / اتریوم / بیت‌کوین / سهام / دلار / نفت / اقتصاد

📈 جهت احتمالی اثر
مثبت / منفی / خنثی / نامشخص

⚠️ نکته مهم
یک نکته مهم که مخاطب باید بداند.

🔗 اطلاعات بیشتر:
لینک اصلی خبر

#میرزا

اخبار:

{news_text}
"""


    return ask_gemini(prompt)


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    data = {

        "chat_id": CHAT_ID,

        "text": message,

        "disable_web_page_preview": False

    }

    response = requests.post(
        url,
        data=data,
        timeout=30
    )

    response.raise_for_status()

    return True


# =========================================================
# MAIN
# =========================================================

def main():

    print("Starting Mirza News Bot...")

    sent_news = load_sent_news()

    print(
        f"Previously sent news: "
        f"{len(sent_news)}"
    )

    # دریافت اخبار
    news = get_news()

    print(
        f"Total RSS news found: "
        f"{len(news)}"
    )

    # حذف تکراری‌ها
    news = remove_duplicates(news)

    print(
        f"After duplicate removal: "
        f"{len(news)}"
    )

    # انتخاب کاندیداها
    candidates = prepare_candidates(
        news,
        sent_news
    )

    print(
        f"Candidate news: "
        f"{len(candidates)}"
    )

    if not candidates:

        print(
            "No new candidate news."
        )

        return


    # تحلیل با Gemini
    result = analyze_news(
        candidates
    )

    if not result:

        print(
            "Gemini failed."
        )

        return


    # هیچ خبر مهمی نبود
    if "NO_IMPORTANT_NEWS" in result:

        print(
            "No important news found."
        )

        return


    # ارسال به تلگرام
    try:

        send_telegram(result)

        print(
            "Telegram message sent successfully."
        )

    except Exception as error:

        print(
            f"Telegram error: {error}"
        )

        return


    # لینک‌های کاندیدا را ثبت می‌کنیم
    # تا در اجرای بعدی دوباره بررسی نشوند.

    for item in candidates:

        sent_news.add(
            item["link"]
        )

    save_sent_news(
        sent_news
    )

    print(
        "Finished. Published: 1"
    )


if __name__ == "__main__":

    main()
