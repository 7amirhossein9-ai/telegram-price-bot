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

GEMINI_MODEL = "gemini-3.8-flash"

MAX_CANDIDATES = 10

NEWS_AGE_HOURS = 3

SENT_FILE = "sent_news.txt"


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


# =========================================================
# NEWS SOURCES
# =========================================================

SOURCES = {
    "Reuters": "reuters.com",
    "Bloomberg": "bloomberg.com",
    "CNBC": "cnbc.com",
    "Financial Times": "ft.com",
    "MarketWatch": "marketwatch.com",
    "Investing": "investing.com",
    "Yahoo Finance": "finance.yahoo.com",
    "Wall Street Journal": "wsj.com",
    "CoinDesk": "coindesk.com",
    "Cointelegraph": "cointelegraph.com",
}


# =========================================================
# IMPORTANT KEYWORDS
# =========================================================

KEYWORDS = {

    "crypto": [
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "crypto",
        "cryptocurrency",
        "binance",
        "coinbase",
        "solana",
        "xrp",
        "defi",
        "stablecoin",
        "blockchain",
    ],

    "gold": [
        "gold",
        "bullion",
        "precious metals",
        "silver",
    ],

    "economy": [
        "inflation",
        "interest rate",
        "interest rates",
        "fed",
        "federal reserve",
        "central bank",
        "recession",
        "gdp",
        "employment",
        "jobs",
        "unemployment",
        "consumer confidence",
        "economic growth",
    ],

    "markets": [
        "stock market",
        "stocks",
        "shares",
        "nasdaq",
        "s&p 500",
        "dow jones",
        "wall street",
        "equity",
        "market",
    ],

    "commodities": [
        "oil",
        "crude",
        "opec",
        "natural gas",
        "commodity",
        "commodities",
    ],

    "currency": [
        "dollar",
        "usd",
        "euro",
        "yuan",
        "yen",
        "currency",
        "forex",
    ],

    "geopolitics": [
        "tariff",
        "tariffs",
        "sanctions",
        "war",
        "iran",
        "israel",
        "ukraine",
        "russia",
        "china",
        "united states",
        "trump",
        "xi jinping",
        "trade war",
    ],

    "companies": [
        "apple",
        "microsoft",
        "google",
        "alphabet",
        "amazon",
        "tesla",
        "nvidia",
        "meta",
        "boeing",
        "bank",
        "banks",
        "earnings",
        "revenue",
        "profit",
        "ceo",
    ],
}


# =========================================================
# SOURCE IMPORTANCE
# =========================================================

SOURCE_SCORE = {
    "Reuters": 20,
    "Bloomberg": 19,
    "Financial Times": 18,
    "Wall Street Journal": 18,
    "CNBC": 16,
    "MarketWatch": 15,
    "Yahoo Finance": 14,
    "Investing": 13,
    "CoinDesk": 15,
    "Cointelegraph": 13,
}


# =========================================================
# BASIC CHECK
# =========================================================

def check_environment():

    missing = []

    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")

    if not CHAT_ID:
        missing.append("CHAT_ID")

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if missing:
        print("Missing environment variables:")
        for item in missing:
            print("-", item)

        return False

    return True


# =========================================================
# SENT NEWS
# =========================================================

def load_sent_news():

    if not os.path.exists(SENT_FILE):
        return set()

    try:

        with open(
            SENT_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return {
                line.strip()
                for line in file
                if line.strip()
            }

    except Exception as e:

        print("Error loading sent news:", e)

        return set()


def save_sent_news(sent_news):

    try:

        with open(
            SENT_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            for item in sorted(sent_news):
                file.write(item + "\n")

    except Exception as e:

        print("Error saving sent news:", e)


# =========================================================
# NEWS ID
# =========================================================

def create_news_id(title, link):

    raw = f"{title}|{link}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:20]


# =========================================================
# GOOGLE NEWS RSS
# =========================================================

def get_rss_url(domain):

    query = f"when:2h site:{domain}"

    return (
        "https://news.google.com/rss/search?"
        f"q={requests.utils.quote(query)}"
        "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )


# =========================================================
# CLEAN TITLE
# =========================================================

def clean_title(title):

    if not title:
        return ""

    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    return title


# =========================================================
# INVALID NEWS FILTER
# =========================================================

def is_valid_news(title, link):

    if not title:
        return False

    if len(title) < 20:
        return False

    if not link:
        return False

    lower_title = title.lower()

    bad_patterns = [
        "print edition",
        "wall street journal - wsj",
        " - coindesk",
        " - wsj",
    ]

    for pattern in bad_patterns:

        if lower_title == pattern:
            return False

    if title.strip() == "-":
        return False

    return True


# =========================================================
# PARSE RSS
# =========================================================

def parse_rss(source_name, domain):

    url = get_rss_url(domain)

    try:

        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(compatible; MirzaNewsBot/1.0)"
            }
        )

        response.raise_for_status()

        root = ET.fromstring(
            response.content
        )

    except Exception as e:

        print(
            f"RSS error - {source_name}:",
            e
        )

        return []

    articles = []

    for item in root.findall(".//item")[:8]:

        title_element = item.find("title")
        link_element = item.find("link")
        date_element = item.find("pubDate")
        source_element = item.find("source")

        title = (
            title_element.text
            if title_element is not None
            else ""
        )

        link = (
            link_element.text
            if link_element is not None
            else ""
        )

        pub_date = (
            date_element.text
            if date_element is not None
            else ""
        )

        rss_source = source_name

        if source_element is not None:
            if source_element.text:
                rss_source = source_element.text.strip()

        title = clean_title(title)

        if not is_valid_news(title, link):
            continue

        published = None

        if pub_date:

            try:

                published = parsedate_to_datetime(
                    pub_date
                )

                if published.tzinfo is None:
                    published = published.replace(
                        tzinfo=timezone.utc
                    )

            except Exception:
                published = None

        articles.append({
            "id": create_news_id(
                title,
                link
            ),
            "title": title,
            "link": link,
            "source": source_name,
            "rss_source": rss_source,
            "published": published,
        })

    return articles


# =========================================================
# COLLECT ALL NEWS
# =========================================================

def collect_news():

    all_news = []

    for source_name, domain in SOURCES.items():

        print(
            f"Collecting: {source_name}"
        )

        news = parse_rss(
            source_name,
            domain
        )

        all_news.extend(news)

    return all_news


# =========================================================
# EXACT DUPLICATE REMOVAL
# =========================================================

def remove_duplicates(news):

    seen = set()

    result = []

    for article in news:

        if article["id"] in seen:
            continue

        seen.add(
            article["id"]
        )

        result.append(article)

    return result


# =========================================================
# KEYWORD SCORE
# =========================================================

def keyword_score(title):

    text = title.lower()

    score = 0

    for category, words in KEYWORDS.items():

        category_found = False

        for word in words:

            if word.lower() in text:

                category_found = True

                break

        if category_found:

            if category in [
                "economy",
                "crypto",
                "gold",
                "markets",
                "currency",
                "geopolitics",
            ]:

                score += 5

            else:

                score += 3

    return min(score, 30)


# =========================================================
# RECENCY SCORE
# =========================================================

def recency_score(published):

    if not published:
        return 5

    now = datetime.now(
        timezone.utc
    )

    age_minutes = (
        now - published
    ).total_seconds() / 60

    if age_minutes <= 15:
        return 20

    if age_minutes <= 30:
        return 18

    if age_minutes <= 60:
        return 15

    if age_minutes <= 120:
        return 10

    if age_minutes <= 180:
        return 5

    return 0


# =========================================================
# TITLE SIMILARITY
# =========================================================

def title_words(title):

    words = re.findall(
        r"[a-zA-Z0-9]+",
        title.lower()
    )

    stop_words = {
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "for",
        "and",
        "with",
        "as",
        "is",
        "by",
        "from",
        "at",
        "after",
        "before",
    }

    return {
        word
        for word in words
        if word not in stop_words
    }


def similarity(title1, title2):

    words1 = title_words(title1)
    words2 = title_words(title2)

    if not words1 or not words2:
        return 0

    intersection = len(
        words1 & words2
    )

    union = len(
        words1 | words2
    )

    return intersection / union


# =========================================================
# CROSS SOURCE TREND
# =========================================================

def calculate_cross_source_scores(news):

    scores = {
        article["id"]: 0
        for article in news
    }

    for i in range(len(news)):

        for j in range(i + 1, len(news)):

            article1 = news[i]
            article2 = news[j]

            if (
                article1["source"]
                ==
                article2["source"]
            ):
                continue

            sim = similarity(
                article1["title"],
                article2["title"]
            )

            if sim >= 0.45:

                scores[
                    article1["id"]
                ] += 15

                scores[
                    article2["id"]
                ] += 15

            elif sim >= 0.30:

                scores[
                    article1["id"]
                ] += 8

                scores[
                    article2["id"]
                ] += 8

    return scores


# =========================================================
# FINAL SCORE
# =========================================================

def score_news(news):

    cross_scores = (
        calculate_cross_source_scores(
            news
        )
    )

    for article in news:

        source = article["source"]

        source_score = SOURCE_SCORE.get(
            source,
            10
        )

        article["keyword_score"] = (
            keyword_score(
                article["title"]
            )
        )

        article["recency_score"] = (
            recency_score(
                article["published"]
            )
        )

        article["source_score"] = (
            source_score
        )

        article["cross_source_score"] = (
            cross_scores.get(
                article["id"],
                0
            )
        )

        article["score"] = (
            article["keyword_score"]
            +
            article["recency_score"]
            +
            article["source_score"]
            +
            article["cross_source_score"]
        )

    return sorted(
        news,
        key=lambda x: x["score"],
        reverse=True
    )


# =========================================================
# PREPARE CANDIDATES
# =========================================================

def prepare_candidates(
    news,
    sent_news
):

    now = datetime.now(
        timezone.utc
    )

    candidates = []

    for article in news:

        if article["id"] in sent_news:
            continue

        published = article[
            "published"
        ]

        if published:

            age_hours = (
                now - published
            ).total_seconds() / 3600

            if age_hours > NEWS_AGE_HOURS:
                continue

        candidates.append(
            article
        )

    candidates = score_news(
        candidates
    )

    return candidates[
        :MAX_CANDIDATES
    ]


# =========================================================
# GEMINI
# =========================================================

def analyze_with_gemini(
    candidates
):

    if not candidates:
        return None

    articles_text = []

    for index, article in enumerate(
        candidates,
        start=1
    ):

        articles_text.append(
            f"""
خبر شماره {index}

منبع:
{article["source"]}

عنوان:
{article["title"]}

لینک:
{article["link"]}

امتیاز داخلی:
{article["score"]}
"""
        )

    articles_text = "\n".join(
        articles_text
    )

    prompt = f"""
تو تحلیلگر اخبار اقتصادی و بازارهای مالی برای کانال تلگرامی «میرزا» هستی.

از بین خبرهای زیر فقط مهم‌ترین خبری را انتخاب کن.

معیار انتخاب:

1. اهمیت اقتصادی
2. تأثیر احتمالی بر بازارهای مالی
3. تأثیر بر طلا
4. تأثیر بر بیت‌کوین و رمزارزها
5. تأثیر بر سهام و شرکت‌ها
6. تأثیر بر دلار و ارزها
7. تأثیر بر نفت و کالاها
8. خبرهای بانک‌های مرکزی، نرخ بهره و تورم
9. خبرهای سیاسی فقط در صورتی که اثر اقتصادی یا بازاری داشته باشند
10. خبری که در چند منبع مختلف دیده شده اهمیت بیشتری دارد.

اگر هیچ‌کدام واقعاً مهم نیستند، selected_index را برابر 0 قرار بده.

اگر خبر مهم وجود دارد:

یک تحلیل کوتاه فارسی بنویس.

متن باید:

- فارسی باشد.
- ساده و قابل فهم باشد.
- حدود 150 تا 250 کلمه باشد.
- خبر را خلاصه کند.
- توضیح دهد چرا این خبر مهم است.
- اثر احتمالی آن بر بازار را توضیح دهد.
- درباره طلا، دلار، بیت‌کوین، اتریوم، سهام یا نفت فقط در صورت ارتباط صحبت کند.
- توصیه خرید یا فروش ندهد.
- پیش‌بینی قطعی نکند.
- درباره افراد و سیاستمداران قضاوت سیاسی نکند.
- اگر خبر سیاسی است فقط اثر اقتصادی و بازاری آن را بررسی کند.
- منبع خبر را در انتهای متن ذکر کند.

خروجی فقط JSON معتبر باشد:

{{
  "selected_index": 0,
  "message": ""
}}

یا:

{{
  "selected_index": 3,
  "message": "متن کامل تحلیل"
}}

خبرها:

{articles_text}
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    payload = {

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

            "responseMimeType":
                "application/json",

            "maxOutputTokens":
                1000,

            "thinkingConfig": {
                "thinkingLevel": "low"
            }
        }
    }

    headers = {

        "Content-Type":
            "application/json",

        "x-goog-api-key":
            GEMINI_API_KEY
    }

    max_retries = 4

    delays = [
        15,
        30,
        60,
        90
    ]

    for attempt in range(
        max_retries
    ):

        try:

            print(
                f"Gemini attempt "
                f"{attempt + 1}/{max_retries}"
            )

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=90
            )

            print(
                "Gemini status:",
                response.status_code
            )

            if response.status_code == 200:

                data = response.json()

                text = (
                    data["candidates"][0]
                    ["content"]["parts"][0]
                    ["text"]
                )

                print(
                    "Gemini response received."
                )

                # Remove possible markdown fences
                text = text.strip()

                text = re.sub(
                    r"^```json",
                    "",
                    text,
                    flags=re.IGNORECASE
                )

                text = re.sub(
                    r"^```",
                    "",
                    text
                )

                text = re.sub(
                    r"```$",
                    "",
                    text
                )

                text = text.strip()

                import json

                result = json.loads(
                    text
                )

                return result

            # Temporary errors
            if response.status_code in [
                429,
                500,
                502,
                503,
                504
            ]:

                print(
                    "Gemini temporary error:",
                    response.status_code
                )

                try:

                    print(
                        response.text[:500]
                    )

                except Exception:
                    pass

                if attempt < max_retries - 1:

                    wait_time = delays[
                        attempt
                    ]

                    print(
                        f"Retrying in "
                        f"{wait_time} seconds..."
                    )

                    time.sleep(
                        wait_time
                    )

                    continue

                return None

            # Other errors
            print(
                "Gemini API error:",
                response.status_code
            )

            print(
                response.text[:1000]
            )

            return None

        except requests.exceptions.Timeout:

            print(
                "Gemini request timeout."
            )

            if attempt < max_retries - 1:

                wait_time = delays[
                    attempt
                ]

                print(
                    f"Retrying in "
                    f"{wait_time} seconds..."
                )

                time.sleep(
                    wait_time
                )

            else:

                return None

        except Exception as e:

            print(
                "Gemini exception:",
                e
            )

            return None

    return None


# =========================================================
# TELEGRAM
# =========================================================

def send_telegram(message):

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    payload = {

        "chat_id": CHAT_ID,

        "text": message,

        "disable_web_page_preview": False
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:

            print(
                "Telegram message sent."
            )

            return True

        print(
            "Telegram error:",
            response.status_code
        )

        print(
            response.text[:500]
        )

        return False

    except Exception as e:

        print(
            "Telegram exception:",
            e
        )

        return False


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

    if not check_environment():

        return

    sent_news = load_sent_news()

    print(
        f"Previously published: "
        f"{len(sent_news)}"
    )

    # -----------------------------------------------------
    # COLLECT
    # -----------------------------------------------------

    news = collect_news()

    print(
        f"Total news collected: "
        f"{len(news)}"
    )

    if not news:

        print(
            "No news collected."
        )

        return

    # -----------------------------------------------------
    # REMOVE EXACT DUPLICATES
    # -----------------------------------------------------

    news = remove_duplicates(
        news
    )

    print(
        f"After duplicate removal: "
        f"{len(news)}"
    )

    # -----------------------------------------------------
    # PREPARE CANDIDATES
    # -----------------------------------------------------

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
            "No new important candidates."
        )

        return

    # -----------------------------------------------------
    # SHOW TOP CANDIDATES
    # -----------------------------------------------------

    print()
    print(
        "Top candidates:"
    )

    for i, article in enumerate(
        candidates,
        start=1
    ):

        print(
            f"{i}. "
            f"[{article['score']}] "
            f"{article['source']} - "
            f"{article['title']}"
        )

    print()

    # -----------------------------------------------------
    # GEMINI
    # -----------------------------------------------------

    print(
        "Sending candidates to Gemini..."
    )

    result = analyze_with_gemini(
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

    # -----------------------------------------------------
    # NO IMPORTANT NEWS
    # -----------------------------------------------------

    if selected_index == 0:

        print(
            "Gemini found no important news."
        )

        return

    # -----------------------------------------------------
    # VALIDATE INDEX
    # -----------------------------------------------------

    if not isinstance(
        selected_index,
        int
    ):

        print(
            "Invalid selected index."
        )

        return

    if selected_index < 1:

        print(
            "Invalid selected index."
        )

        return

    if selected_index > len(
        candidates
    ):

        print(
            "Selected index out of range."
        )

        return

    if not message:

        print(
            "Gemini returned empty message."
        )

        return

    # -----------------------------------------------------
    # SELECTED ARTICLE
    # -----------------------------------------------------

    selected_article = candidates[
        selected_index - 1
    ]

    print()
    print(
        "Selected news:"
    )

    print(
        selected_article["title"]
    )

    print(
        "Source:",
        selected_article["source"]
    )

    # -----------------------------------------------------
    # SEND TELEGRAM
    # -----------------------------------------------------

    success = send_telegram(
        message
    )

    if not success:

        print(
            "Telegram sending failed."
        )

        return

    # -----------------------------------------------------
    # SAVE ONLY SENT NEWS
    # -----------------------------------------------------

    sent_news.add(
        selected_article["id"]
    )

    save_sent_news(
        sent_news
    )

    print(
        "News saved as published."
    )

    print(
        "================================"
    )

    print(
        "Bot finished successfully."
    )

    print(
        "================================"
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
