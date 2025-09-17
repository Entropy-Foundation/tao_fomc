import argparse
import time
from datetime import datetime, timedelta, timezone

import requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None

if ZoneInfo is not None:
    _TARGET_ZONE = ZoneInfo("America/New_York")
else:
    _TARGET_ZONE = timezone(timedelta(hours=-4))

TARGET_ANNOUNCEMENT_TIME = datetime(2025, 9, 17, 14, tzinfo=_TARGET_ZONE)
TARGET_ANNOUNCEMENT_TIME_UTC = TARGET_ANNOUNCEMENT_TIME.astimezone(timezone.utc)
DEFAULT_POLL_INTERVAL_SECONDS = 60

def get_fomc_news():
    """
    Retrieves the latest news from the FOMC RSS feed.

    Returns:
        A list of dictionaries, where each dictionary represents a news item
        and has the following keys:
            - title: The title of the news item.
            - link: The URL of the news item.
            - pub_date: The publication date of the news item.
    """
    url = "https://www.federalreserve.gov/feeds/press_all.xml"
    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException:
        return []

    if response.status_code != 200:
        return []

    root = ET.fromstring(response.content)
    news_items = []
    for item in root.findall(".//item"):
        news_item = {
            "title": item.find("title").text,
            "link": item.find("link").text,
            "pub_date": item.find("pubDate").text
        }
        news_items.append(news_item)
    return news_items

def filter_news(news_items, keywords):
    filtered_news = []
    for item in news_items:
        title = item.get('title', '').lower()

        # Check if all keywords are in the title
        if all(keyword.lower() in title for keyword in keywords):
            filtered_news.append(item)
            
    return filtered_news


def _parse_pub_date(pub_date_str):
    try:
        return parsedate_to_datetime(pub_date_str)
    except (TypeError, ValueError):
        return None


def _find_target_link(news_items, target_utc):
    dated_items = []

    for item in news_items:
        pub_date = _parse_pub_date(item.get("pub_date"))
        if not pub_date:
            continue

        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)

        pub_date_utc = pub_date.astimezone(timezone.utc)
        dated_items.append((pub_date_utc, item))

    for pub_date_utc, item in sorted(dated_items, key=lambda pair: pair[0], reverse=True):
        if pub_date_utc >= target_utc:
            return item.get("link")

    return None

def main(poll_interval):
    keywords = ["FOMC", "statement"]

    while True:
        latest_news = get_fomc_news()
        if latest_news:
            filtered_articles = filter_news(latest_news, keywords=keywords)
            link = _find_target_link(filtered_articles, TARGET_ANNOUNCEMENT_TIME_UTC)
            if link:
                print(link)
                break

        time.sleep(poll_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor FOMC RSS feed for the September 17, 2025 announcement.")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Polling interval in seconds (default: %(default)s)",
    )

    args = parser.parse_args()
    poll_interval = max(1, args.interval)
    main(poll_interval)
