"""
Multi-source news and social media scanner for master list stocks.

Sources:
  - Yahoo Finance (via yfinance, free)
  - Google News RSS (free)
  - X / Twitter (v2 recent search, requires TWITTER_BEARER_TOKEN)

Deduplication: article URLs are hashed and stored in Redis (TTL 24h) so each
article triggers a notification only once per day.
"""
import asyncio
import hashlib
import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InvestmentAI/1.0; research bot)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search"
    "?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
)


# ─── Source fetchers ─────────────────────────────────────────────────────────

async def _fetch_yahoo_news(symbol: str) -> List[Dict]:
    """yfinance .news — synchronous, run in thread pool."""
    def _sync():
        try:
            import yfinance as yf
            news = yf.Ticker(symbol).news or []
            out = []
            for item in news[:6]:
                url = item.get("link") or item.get("url", "")
                if url:
                    out.append({
                        "url": url,
                        "title": item.get("title", ""),
                        "source": "Yahoo Finance",
                        "symbol": symbol,
                    })
            return out
        except Exception as exc:
            logger.debug(f"Yahoo news: {symbol}: {exc}")
            return []

    return await asyncio.to_thread(_sync)


async def _fetch_google_news(symbol: str) -> List[Dict]:
    """Google News RSS filtered by symbol."""
    try:
        url = _GOOGLE_NEWS_RSS.format(symbol=symbol)
        async with httpx.AsyncClient(timeout=10, headers=_HTTP_HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        out = []
        for item in root.findall(".//item")[:6]:
            link = item.findtext("link", "")
            title = item.findtext("title", "")
            if link and title:
                out.append({"url": link, "title": title, "source": "Google News", "symbol": symbol})
        return out
    except Exception as exc:
        logger.debug(f"Google News RSS: {symbol}: {exc}")
        return []


async def _fetch_twitter(symbol: str, bearer_token: str) -> List[Dict]:
    """Twitter/X v2 recent search — high-engagement posts only (≥10 likes+RTs)."""
    if not bearer_token:
        return []
    try:
        query = f"(${symbol} OR #{symbol}) -is:retweet lang:en"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.twitter.com/2/tweets/search/recent",
                params={
                    "query": query,
                    "max_results": 10,
                    "tweet.fields": "created_at,public_metrics",
                },
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
        if resp.status_code == 429:
            logger.warning(f"Twitter rate-limit for {symbol}")
            return []
        resp.raise_for_status()

        out = []
        for tweet in resp.json().get("data", []):
            m = tweet.get("public_metrics", {})
            engagement = m.get("like_count", 0) + m.get("retweet_count", 0)
            if engagement < 10:
                continue
            out.append({
                "url": f"https://x.com/i/web/status/{tweet['id']}",
                "title": tweet.get("text", "")[:200],
                "source": "X (Twitter)",
                "symbol": symbol,
                "engagement": engagement,
            })
        return out
    except Exception as exc:
        logger.debug(f"Twitter: {symbol}: {exc}")
        return []


# ─── Deduplication + main entry ──────────────────────────────────────────────

def _article_id(article: Dict) -> str:
    return hashlib.md5(article["url"].encode()).hexdigest()


async def get_new_articles(
    symbol: str,
    redis_client,
    bearer_token: str = "",
) -> List[Dict]:
    """
    Fetch all sources concurrently, return only articles not seen before.
    Marks new article IDs as seen in Redis with a 24h TTL.
    """
    redis_key = f"investment_ai:news_seen:{symbol}"

    fetchers = [_fetch_yahoo_news(symbol), _fetch_google_news(symbol)]
    if bearer_token:
        fetchers.append(_fetch_twitter(symbol, bearer_token))

    results = await asyncio.gather(*fetchers, return_exceptions=True)

    all_articles: List[Dict] = []
    for r in results:
        if isinstance(r, list):
            all_articles.extend(r)

    new_articles: List[Dict] = []
    for article in all_articles:
        aid = _article_id(article)
        added = await redis_client.sadd(redis_key, aid)
        if added:
            new_articles.append(article)

    if new_articles:
        await redis_client.expire(redis_key, 86400)

    return new_articles
