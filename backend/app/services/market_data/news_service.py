"""
News Service
Aggregates financial news from NewsAPI and Israeli financial RSS feeds.
"""
import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import structlog
import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.agents.state import NewsItem

logger = structlog.get_logger(__name__)

# Israeli financial news RSS feeds
ISRAELI_RSS_FEEDS = [
    {
        "name": "Calcalist",
        "url": "https://www.calcalist.co.il/home/0,7340,L-8,00.xml",
        "language": "he",
    },
    {
        "name": "Globes",
        "url": "https://www.globes.co.il/webservice/rss/rssfeeder.asmx/FeederNode?iID=1111",
        "language": "he",
    },
    {
        "name": "TheMarker",
        "url": "https://www.themarker.com/srv/rss-feed",
        "language": "he",
    },
]

BULLISH_WORDS = {
    "growth", "profit", "gain", "revenue", "beat", "record", "upgrade",
    "positive", "strong", "rise", "rally", "buy", "outperform", "surge",
    "earnings", "acquisition", "partnership", "innovation", "expansion"
}
BEARISH_WORDS = {
    "loss", "decline", "miss", "downgrade", "negative", "weak", "fall",
    "lawsuit", "fraud", "investigation", "layoffs", "debt", "bankruptcy",
    "warning", "concern", "risk", "regulatory", "fine", "scandal"
}


def _simple_sentiment(text: str) -> float:
    """Simple keyword-based article sentiment."""
    text_lower = text.lower()
    words = set(re.findall(r'\b\w+\b', text_lower))
    bull = len(words & BULLISH_WORDS)
    bear = len(words & BEARISH_WORDS)
    total = bull + bear
    if total == 0:
        return 0.0
    return round((bull - bear) / total, 3)


class NewsService:
    """Aggregates news from NewsAPI and Israeli RSS feeds."""

    def __init__(self):
        self._newsapi_enabled = bool(settings.NEWSAPI_KEY)
        self._timeout = httpx.Timeout(20.0)

    async def get_news(self, symbol: str, days_back: int = 7) -> List[NewsItem]:
        """
        Fetch recent news articles for the given stock symbol.
        Returns list of NewsItem dicts sorted by recency.
        """
        from app.services.market_data.finnhub_service import get_finnhub_service
        tasks = [
            self._fetch_newsapi(symbol, days_back),
            self._fetch_israeli_rss(symbol),
            get_finnhub_service().get_news(symbol, days_back),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_articles: List[NewsItem] = []
        for result in results:
            if isinstance(result, list):
                all_articles.extend(result)
            elif isinstance(result, Exception):
                logger.debug("News fetch error", error=str(result))

        # Sort by published_at descending, deduplicate by title
        seen_titles = set()
        unique_articles: List[NewsItem] = []
        for article in sorted(all_articles, key=lambda x: x.get("published_at", ""), reverse=True):
            title = article.get("title", "").lower()[:80]
            if title not in seen_titles:
                seen_titles.add(title)
                unique_articles.append(article)

        return unique_articles[:30]

    async def _fetch_newsapi(self, symbol: str, days_back: int) -> List[NewsItem]:
        """Fetch from NewsAPI."""
        if not self._newsapi_enabled:
            return []

        try:
            from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": f"{symbol} stock",
                        "from": from_date,
                        "sortBy": "publishedAt",
                        "language": "en",
                        "pageSize": 30,
                        "apiKey": settings.NEWSAPI_KEY,
                    },
                )

                if resp.status_code != 200:
                    logger.warning("NewsAPI returned non-200", status=resp.status_code)
                    return []

                data = resp.json()
                articles = data.get("articles", [])

                news_items: List[NewsItem] = []
                for article in articles:
                    title = article.get("title") or ""
                    description = article.get("description") or ""
                    content = article.get("content") or description
                    summary = description[:500] if description else title

                    full_text = f"{title} {description}"
                    sentiment_score = _simple_sentiment(full_text)

                    published_at = article.get("publishedAt", "")

                    news_items.append(NewsItem(
                        title=title[:300],
                        source=article.get("source", {}).get("name", "NewsAPI"),
                        url=article.get("url", ""),
                        published_at=published_at,
                        summary=summary[:600],
                        sentiment=sentiment_score,
                    ))

                return news_items

        except Exception as e:
            logger.error("NewsAPI fetch failed", symbol=symbol, error=str(e))
            return []

    async def _fetch_israeli_rss(self, symbol: str) -> List[NewsItem]:
        """Fetch from Israeli financial news RSS feeds, filtering for relevant content."""
        articles: List[NewsItem] = []

        # Only fetch Israeli RSS for TASE stocks or well-known Israeli companies
        israel_keywords = {"tase", "תל אביב", "בורסה", "שקל", "nis", symbol.lower()}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for feed in ISRAELI_RSS_FEEDS:
                try:
                    resp = await client.get(feed["url"])
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "xml")
                    items = soup.find_all("item")

                    for item in items[:20]:
                        title_tag = item.find("title")
                        desc_tag = item.find("description")
                        link_tag = item.find("link")
                        date_tag = item.find("pubDate")

                        title = title_tag.get_text(strip=True) if title_tag else ""
                        description = desc_tag.get_text(strip=True) if desc_tag else ""
                        link = link_tag.get_text(strip=True) if link_tag else ""
                        pub_date = date_tag.get_text(strip=True) if date_tag else ""

                        combined = f"{title} {description}".lower()

                        # Check relevance
                        is_relevant = (
                            symbol.lower() in combined or
                            any(kw in combined for kw in israel_keywords)
                        )

                        if is_relevant:
                            sentiment_score = _simple_sentiment(combined)
                            articles.append(NewsItem(
                                title=title[:300],
                                source=feed["name"],
                                url=link,
                                published_at=pub_date,
                                summary=description[:500],
                                sentiment=sentiment_score,
                            ))

                except Exception as e:
                    logger.debug("RSS feed fetch failed", feed=feed["name"], error=str(e))
                    continue

        return articles
