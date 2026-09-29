import os
import time
import re
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# مدل فعلی Gemini
GEMINI_MODEL = "gemini-3.8-flash"

# در هر اجرای GitHub حداکثر این تعداد خبر
# برای Gemini فرستاده می‌شود.
MAX_CANDIDATES = 15

# فایل اخبار منتشرشده
SENT_FILE = "sent_news.txt"

# چند خبر از هر سایت بگیریم
NEWS_PER_SOURCE = 5


# =========================================================
# NEWS SOURCES
# =========================================================

SOURCES = {

    "Reuters":
        "reuters.com",

    "Bloomberg":
        "bloomberg.com",

    "CNBC":
        "cnbc.com",

    "Financial Times":
        "ft.com",

    "MarketWatch":
        "marketwatch.com",

    "Investing":
        "investing.com",

    "Yahoo Finance":
        "finance.yahoo.com",

    "Wall Street Journal":
        "wsj.com",

    "CoinDesk":
        "coindesk.com",

    "Cointelegraph":
        "cointelegraph.com",

}


# =========================================================
# IMPORTANT KEYWORDS
# =========================================================

KEYWORDS = {

    # Crypto
    "bitcoin": 12,
    "btc": 12,
    "ethereum": 12,
    "eth": 12,
    "crypto": 10,
    "cryptocurrency": 10,
    "solana": 8,
    "xrp": 8,

    # Gold
    "gold": 12,
    "gold prices": 15,
    "bullion": 10,
    "silver": 7,

    # Economy
    "inflation": 12,
    "interest rate": 14,
    "interest rates": 14,
    "fed": 14,
    "federal reserve": 15,
    "ecb": 12,
    "central bank": 12,
    "recession": 13,
    "gdp": 10,
    "employment": 9,
    "unemployment": 10,
    "jobs report": 12,

    # Markets
    "stock market": 12,
    "stocks": 9,
    "shares": 8,
    "nasdaq": 10,
    "s&p 500": 10,
    "dow jones": 9,
    "wall street": 10,

    # Commodities
    "oil": 10,
    "crude": 10,
    "opec": 12,
    "natural gas": 8,

    # Dollar / currencies
    "dollar": 10,
    "usd": 8,
    "forex": 8,
    "currency": 7,

    # Geopolitics / politics with economic impact
    "tariff": 14,
    "tariffs": 14,
    "sanction": 13,
    "sanctions": 13,
    "trade war": 15,
    "war": 12,
    "conflict": 10,
    "iran": 12,
    "israel": 10,
    "russia": 10,
    "ukraine": 10,
    "china": 10,
    "united states": 7,
    "trump": 8,
    "election": 8,

    # Companies
    "earnings": 10,
    "revenue": 8,
    "profit": 8,
    "merger": 10,
    "acquisition": 10,
    "ipo": 10,
    "bankruptcy": 12,

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

    with open(
        SENT_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return set(
            line.strip()
            for line in file
            if line.strip()
        )


def save_sent_news(sent_news):

    with open(
        SENT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        for item in sorted(sent_news):

            file.write(
                item + "\n"
            )


# =========================================================
# GOOGLE NEWS RSS
# =========================================================

def build_google_news_url(domain):

    query = (
        f"when:2h site:{domain}"
    )

    return (
        "https://news.google.com/rss/search?"
        f"q={requests.utils.quote(query)}"
        "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )


# =========================================================
# DATE PARSER
# =========================================================

def parse_date(date_string):

    if not date_string:

        return None

    try:

        dt = parsedate_to_datetime(
            date_string
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:

        return None


# =========================================================
# NEWS ID
# =========================================================

def create_news_id(title, link):

    raw = (
        title.strip().lower()
        + "|"
        + link.strip().lower()
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# =========================================================
# RSS READER
# =========================================================

def get_news():

    all_news = []

    for source, domain in SOURCES.items():

        url = build_google_news_url(
            domain
        )

        try:

            response = requests.get(
                url,
                timeout=20,
                headers={
                    "User-Agent":
                    "Mozilla/5.0"
                }
            )

            response.raise_for_status()

            root = ET.fromstring(
                response.content
            )

            items = root.findall(
                ".//item"
            )

            count = 0

            for item in items:

                if count >= NEWS_PER_SOURCE:
                    break

                title = item.findtext(
                    "title"
                )

                link = item.findtext(
                    "link"
                )

                description = item.findtext(
                    "description"
                )

                pub_date = item.findtext(
                    "pubDate"
                )

                if not title or not link:
                    continue

                title = title.strip()

                link = link.strip()

                description = (
                    description.strip()
                    if description
                    else ""
                )

                pub_date = (
                    pub_date.strip()
                    if pub_date
                    else ""
                )

                news_id = create_news_id(
                    title,
                    link
                )

                all_news.append({

                    "id": news_id,

                    "source": source,

                    "domain": domain,

                    "title": title,

                    "description":
                        description,

                    "link": link,

                    "pub_date":
                        pub_date,

                })

                count += 1

        except Exception as error:

            print(
                f"RSS error [{source}]: "
                f"{error}"
            )

    return all_news


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# DUPLICATE TITLE CHECK
# =========================================================

def normalize_title(title):

    title = title.lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


def title_words(title):

    return set(
        normalize_title(title)
        .split()
    )


def similarity(title1, title2):

    words1 = title_words(title1)

    words2 = title_words(title2)

    if not words1 or not words2:

        return 0

    intersection = (
        words1 & words2
    )

    union = (
        words1 | words2
    )

    return (
        len(intersection)
        /
        len(union)
    )


# =========================================================
# REMOVE EXACT DUPLICATES
# =========================================================

def remove_duplicates(news):

    result = []

    seen_ids = set()

    for item in news:

        if item["id"] in seen_ids:
            continue

        seen_ids.add(
            item["id"]
        )

        result.append(
            item
        )

    return result


# =========================================================
# TREND / IMPORTANCE SCORE
# =========================================================

def calculate_keyword_score(item):

    text = (
        item["title"]
        + " "
        + item["description"]
    ).lower()

    score = 0

    for keyword, value in KEYWORDS.items():

        if keyword in text:

            score += value

    return score


def calculate_recency_score(item):

    dt = parse_date(
        item["pub_date"]
    )

    if not dt:

        return 0

    now = datetime.now(
        timezone.utc
    )

    age_minutes = (
        now - dt
    ).total_seconds() / 60

    if age_minutes < 15:

        return 25

    if age_minutes < 30:

        return 22

    if age_minutes < 60:

        return 18

    if age_minutes < 120:

        return 12

    if age_minutes < 180:

        return 7

    return 0


def calculate_source_score(item):

    important_sources = {

        "Reuters": 15,

        "Bloomberg": 15,

        "Financial Times": 13,

        "Wall Street Journal": 13,

        "CNBC": 12,

        "MarketWatch": 10,

        "Yahoo Finance": 9,

        "Investing": 8,

        "CoinDesk": 10,

        "Cointelegraph": 8,

    }

    return important_sources.get(
        item["source"],
        5
    )


# =========================================================
# CROSS-SOURCE TREND SCORE
# =========================================================

def calculate_cross_source_scores(news):

    scores = {
        item["id"]: 0
        for item in news
    }

    for i in range(
        len(news)
    ):

        for j in range(
            i + 1,
            len(news)
        ):

            similarity_score = similarity(
                news[i]["title"],
                news[j]["title"]
            )

            # اگر دو عنوان خیلی شبیه باشند،
            # احتمالاً درباره یک اتفاق هستند.

            if similarity_score >= 0.45:

                scores[
                    news[i]["id"]
                ] += 15

                scores[
                    news[j]["id"]
                ] += 15

    return scores


# =========================================================
# BUILD TREND SCORE
# =========================================================

def score_news(news):

    cross_scores = (
        calculate_cross_source_scores(
            news
        )
    )

    for item in news:

        keyword_score = (
            calculate_keyword_score(
                item
            )
        )

        recency_score = (
            calculate_recency_score(
                item
            )
        )

        source_score = (
            calculate_source_score(
                item
            )
        )

        cross_source_score = (
            cross_scores[
                item["id"]
            ]
        )

        total = (
            keyword_score
            + recency_score
            + source_score
            + cross_source_score
        )

        item[
            "keyword_score"
        ] = keyword_score

        item[
            "recency_score"
        ] = recency_score

        item[
            "source_score"
        ] = source_score

        item[
            "cross_source_score"
        ] = cross_source_score

        item[
            "trend_score"
        ] = total

    news.sort(
        key=lambda x:
            x["trend_score"],
        reverse=True
    )

    return news


# =========================================================
# PREPARE CANDIDATES
# =========================================================

def prepare_candidates(
    news,
    sent_news
):

    candidates = []

    for item in news:

        # خبر قبلاً منتشر شده
        if item["id"] in sent_news:
            continue

        # خبر خیلی قدیمی
        dt = parse_date(
            item["pub_date"]
        )

        if dt:

            age_hours = (
                datetime.now(
                    timezone.utc
                ) - dt
            ).total_seconds() / 3600

            if age_hours > 3:

                continue

        candidates.append(
            item
        )

    candidates = score_news(
        candidates
    )

    return candidates[
        :MAX_CANDIDATES
    ]


# =========================================================
# GEMINI API
# =========================================================

def ask_gemini(prompt):

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}"
        ":generateContent"
    )

    headers = {

        "Content-Type":
            "application/json"

    }

    params = {

        "key":
            GEMINI_API_KEY

    }

    data = {

        "contents": [

            {

                "parts": [

                    {
                        "text":
                            prompt
                    }

                ]

            }

        ],

        "generationConfig": {

            "temperature":
                0.2,

            "maxOutputTokens":
                1200,

            "responseMimeType":
                "application/json"

        }

    }

    for attempt in range(3):

        try:

            response = requests.post(

                url,

                params=params,

                headers=headers,

                json=data,

                timeout=90

            )

            if response.status_code in [
                429,
                503
            ]:

                print(
                    "Gemini temporary error: "
                    f"{response.status_code}"
                )

                if attempt < 2:

                    time.sleep(20)

                    continue

                return None

            response.raise_for_status()

            result = response.json()

            text = (
                result[
                    "candidates"
                ][0][
                    "content"
                ][
                    "parts"
                ][0][
                    "text"
                ]
            )

            return text

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
# GEMINI ANALYSIS
# =========================================================

def analyze_candidates(
    candidates
):

    news_text = ""

    for index, item in enumerate(
        candidates,
        start=1
    ):

        news_text += f"""

خبر شماره {index}

منبع:
{item["source"]}

عنوان:
{item["title"]}

توضیح:
{clean_text(item["description"])}

زمان:
{item["pub_date"]}

امتیاز ترند اولیه:
{item["trend_score"]}

امتیاز کلمات کلیدی:
{item["keyword_score"]}

امتیاز تازگی:
{item["recency_score"]}

امتیاز منبع:
{item["source_score"]}

امتیاز پوشش چندمنبعی:
{item["cross_source_score"]}

لینک:
{item["link"]}

--------------------------------
"""


    prompt = f"""
تو سردبیر حرفه‌ای کانال اقتصادی «میرزا» هستی.

از بین خبرهای زیر مهم‌ترین خبر جدید و
قابل انتشار را انتخاب کن.

موضوعات مورد توجه:

- اقتصاد
- سیاست مؤثر بر اقتصاد
- طلا
- بیت‌کوین
- اتریوم
- رمزارزها
- بورس
- سهام شرکت‌ها
- دلار و ارز
- نفت
- بانک‌های مرکزی
- نرخ بهره
- تورم
- تعرفه
- تحریم
- جنگ و ژئوپلیتیک با اثر اقتصادی
- شرکت‌های بزرگ

معیار انتخاب:

1. اهمیت خبر
2. تازگی
3. اثر احتمالی بر بازار
4. میزان توجه احتمالی بازار
5. پوشش شدن خبر توسط چند منبع
6. ارتباط با دارایی‌های مهم
7. معتبر بودن منبع
8. جدید بودن اتفاق

فقط به عدد امتیاز اولیه اعتماد نکن.
خودت خبر را بررسی و مقایسه کن.

اگر هیچ خبر مهمی وجود ندارد:

selected_index = 0

قرار بده.

اگر خبر مهم وجود دارد:
شماره آن را انتخاب کن.

اگر چند منبع درباره یک اتفاق مشابه
خبر داده‌اند، آن اتفاق را ترندتر در نظر بگیر.

------------------------------

قوانین تحلیل:

اگر خبر درباره طلا است:

- علت اهمیت خبر را توضیح بده.
- ارتباط احتمالی با دلار، نرخ بهره،
تورم و ریسک جهانی را بررسی کن.

اگر درباره بیت‌کوین یا اتریوم است:

- اتفاق را توضیح بده.
- دلیل اهمیت آن را بگو.
- اثر احتمالی روی کریپتو را توضیح بده.

اگر درباره سهام یا شرکت است:

- نام شرکت را واضح بنویس.
- اگر نماد سهم در خبر وجود دارد،
  نماد را بنویس.
- اثر احتمالی خبر روی شرکت یا صنعت
  را توضیح بده.
- لینک اصلی خبر را ارائه کن.

اگر خبر سیاسی است:

فقط اثر اقتصادی و بازار آن را توضیح بده.

از حمایت یا مخالفت سیاسی خودداری کن.

هیچ توصیه خرید یا فروش نده.

متن فارسی باشد.

کوتاه و کاربردی باشد.

حدود 150 تا 250 کلمه.

------------------------------

ساختار پیام:

🔥 تیتر

📰 چه اتفاقی افتاده؟

📊 تحلیل میرزا

🎯 بازار مرتبط

📈 جهت احتمالی اثر:
مثبت / منفی / خنثی / نامشخص

⚠️ نکته مهم

🔗 اطلاعات بیشتر:
لینک اصلی

#میرزا

------------------------------

فقط JSON معتبر برگردان:

{{
    "selected_index": 1,
    "message": "متن کامل پیام"
}}

اگر هیچ خبر مهمی وجود ندارد:

{{
    "selected_index": 0,
    "message": ""
}}

اخبار:

{news_text}
"""


    response = ask_gemini(
        prompt
    )

    if not response:

        return None

    try:

        import json

        data = json.loads(
            response
        )

        return data

    except Exception as error:

        print(
            f"JSON parsing error: "
            f"{error}"
        )

        print(
            "Gemini response:"
        )

        print(response)

        return None


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

    data = {

        "chat_id":
            CHAT_ID,

        "text":
            message,

        "disable_web_page_preview":
            False

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

    print(
        "================================"
    )

    print(
        "Starting Mirza News Bot"
    )

    print(
        "================================"
    )


    # ---------------------------------
    # Previous news
    # ---------------------------------

    sent_news = load_sent_news()

    print(
        f"Previously published: "
        f"{len(sent_news)}"
    )


    # ---------------------------------
    # Get news
    # ---------------------------------

    news = get_news()

    print(
        f"Total news collected: "
        f"{len(news)}"
    )


    if not news:

        print(
            "No news collected."
        )

        return


    # ---------------------------------
    # Remove duplicates
    # ---------------------------------

    news = remove_duplicates(
        news
    )

    print(
        f"After duplicate removal: "
        f"{len(news)}"
    )


    # ---------------------------------
    # Candidates
    # ---------------------------------

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


    # ---------------------------------
    # Show candidates
    # ---------------------------------

    print(
        "\nTop candidates:"
    )

    for index, item in enumerate(
        candidates,
        start=1
    ):

        print(
            f"{index}. "
            f"[{item['trend_score']}] "
            f"{item['source']} - "
            f"{item['title']}"
        )


    # ---------------------------------
    # Gemini
    # ---------------------------------

    print(
        "\nSending candidates to Gemini..."
    )

    result = analyze_candidates(
        candidates
    )


    if not result:

        print(
            "Gemini analysis failed."
        )

        return


    selected_index = result.get(
        "selected_index",
        0
    )

    message = result.get(
        "message",
        ""
    )


    print(
        f"Gemini selected: "
        f"{selected_index}"
    )


    # ---------------------------------
    # No important news
    # ---------------------------------

    if selected_index == 0:

        print(
            "No important news."
        )

        return


    if not message:

        print(
            "Empty message."
        )

        return


    # ---------------------------------
    # Validate index
    # ---------------------------------

    if (
        selected_index < 1
        or
        selected_index > len(candidates)
    ):

        print(
            "Invalid selected index."
        )

        return


    # ---------------------------------
    # Selected article
    # ---------------------------------

    selected_article = candidates[
        selected_index - 1
    ]

    selected_id = (
        selected_article["id"]
    )


    # ---------------------------------
    # Send Telegram
    # ---------------------------------

    try:

        send_telegram(
            message
        )

        print(
            "Telegram message sent."
        )

    except Exception as error:

        print(
            f"Telegram error: "
            f"{error}"
        )

        return


    # ---------------------------------
    # SAVE ONLY SELECTED NEWS
    # ---------------------------------

    sent_news.add(
        selected_id
    )

    save_sent_news(
        sent_news
    )


    print(
        "Selected news saved."
    )

    print(
        "Finished. Published: 1"
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
