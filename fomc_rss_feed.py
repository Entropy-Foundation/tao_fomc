import requests
import xml.etree.ElementTree as ET

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
    response = requests.get(url)

    if response.status_code == 200:
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
    else:
        print(f"Failed to retrieve RSS feed. Status code: {response.status_code}")
        return []

def filter_news(news_items, keywords):
    filtered_news = []
    for item in news_items:
        title = item.get('title', '').lower()
        
        # Check if all keywords are in the title
        if all(keyword.lower() in title for keyword in keywords):
            filtered_news.append(item)
            
    return filtered_news

if __name__ == "__main__":
    latest_news = get_fomc_news()
    if latest_news:
        # Filter for news related to interest rate reduction
        filtered_articles = filter_news(latest_news, keywords=["FOMC", "statement"])
        
        if filtered_articles:
            for item in filtered_articles:
                print(f"Title: {item['title']}\nLink: {item['link']}\nDate: {item['pub_date']}\n---")
        else:
            print("No articles found matching the criteria.")
