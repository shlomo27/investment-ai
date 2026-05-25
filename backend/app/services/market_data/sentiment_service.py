"""
Social Sentiment Service
Aggregates sentiment from Twitter/X and Reddit.
Calculates a composite sentiment score from -1 (very bearish) to +1 (very bullish).
"""
import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import structlog

from app.core.config import settings
from app.agents.state import SocialSentiment

logger = structlog.get_logger(__name__)

# Simple keyword-based sentiment scoring as fallback
BULLISH_WORDS = {
    "buy", "bull", "bullish", "long", "moon", "pump", "calls", "upside",
    "undervalued", "growth", "strong", "positive", "gain", "profit", "beat",
    "outperform", "upgrade", "revenue", "earnings beat", "record", "rally"
}
BEARISH_WORDS = {
    "sell", "bear", "bearish", "short", "dump", "puts", "downside",
    "overvalued", "decline", "weak", "negative", "loss", "miss", "fail",
    "underperform", "downgrade", "lawsuit", "fraud", "bankruptcy", "crash"
}


def _score_text(text: str) -> float:
    """Simple keyword-based sentiment scoring."""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    word_set = set(words)
    bull_count = len(word_set & BULLISH_WORDS)
    bear_count = len(word_set & BEARISH_WORDS)
    total = bull_count + bear_count
    if total == 0:
        return 0.0
    return (bull_count - bear_count) / total


class SentimentService:
    """
    Aggregates social sentiment from Twitter/X and Reddit.
    """

    def __init__(self):
        self._twitter_client = None
        self._reddit_client = None
        self._twitter_enabled = bool(settings.TWITTER_BEARER_TOKEN)
        self._reddit_enabled = bool(
            settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET
        )

    def _get_twitter_client(self):
        """Lazy-initialize Tweepy client."""
        if self._twitter_client is None and self._twitter_enabled:
            try:
                import tweepy
                self._twitter_client = tweepy.Client(
                    bearer_token=settings.TWITTER_BEARER_TOKEN,
                    wait_on_rate_limit=False,
                )
            except Exception as e:
                logger.warning("Tweepy client init failed", error=str(e))
                self._twitter_enabled = False
        return self._twitter_client

    def _get_reddit_client(self):
        """Lazy-initialize PRAW client."""
        if self._reddit_client is None and self._reddit_enabled:
            try:
                import praw
                self._reddit_client = praw.Reddit(
                    client_id=settings.REDDIT_CLIENT_ID,
                    client_secret=settings.REDDIT_CLIENT_SECRET,
                    user_agent=settings.REDDIT_USER_AGENT,
                )
            except Exception as e:
                logger.warning("PRAW client init failed", error=str(e))
                self._reddit_enabled = False
        return self._reddit_client

    async def get_sentiment(self, symbol: str) -> SocialSentiment:
        """
        Main method: fetch sentiment from all social platforms.
        Returns aggregated SocialSentiment.
        """
        tasks = [
            self._get_twitter_sentiment(symbol),
            self._get_reddit_sentiment(symbol),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        twitter_result = results[0] if not isinstance(results[0], Exception) else {"score": 0.0, "count": 0, "posts": [], "themes": []}
        reddit_result = results[1] if not isinstance(results[1], Exception) else {"score": 0.0, "count": 0, "posts": [], "themes": []}

        twitter_score = twitter_result.get("score", 0.0)
        twitter_count = twitter_result.get("count", 0)
        reddit_score = reddit_result.get("score", 0.0)
        reddit_count = reddit_result.get("count", 0)

        total_count = twitter_count + reddit_count

        # Weighted composite score (Twitter has higher volume, Reddit has deeper analysis)
        if total_count > 0:
            composite_score = (
                (twitter_score * twitter_count * 0.4 + reddit_score * reddit_count * 0.6)
                / max(total_count, 1)
            )
        else:
            composite_score = 0.0

        # Clamp to [-1, 1]
        composite_score = max(-1.0, min(1.0, composite_score))

        # Trending: more than 100 mentions in last 24h
        is_trending = total_count > 100

        # Combine top posts
        all_posts = twitter_result.get("posts", [])[:3] + reddit_result.get("posts", [])[:3]

        # Combine themes
        all_themes = list(set(
            twitter_result.get("themes", []) + reddit_result.get("themes", [])
        ))[:10]

        return SocialSentiment(
            score=round(composite_score, 4),
            mentions=total_count,
            trending=is_trending,
            top_posts=all_posts[:6],
            key_themes=all_themes,
            twitter_score=round(twitter_score, 4),
            reddit_score=round(reddit_score, 4),
            tweet_count=twitter_count,
            reddit_post_count=reddit_count,
        )

    async def _get_twitter_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Fetch and score tweets about the symbol."""
        if not self._twitter_enabled:
            return {"score": 0.0, "count": 0, "posts": [], "themes": []}

        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._fetch_twitter_sync(symbol)
            )
        except Exception as e:
            logger.warning("Twitter sentiment failed", symbol=symbol, error=str(e))
            return {"score": 0.0, "count": 0, "posts": [], "themes": []}

    def _fetch_twitter_sync(self, symbol: str) -> Dict[str, Any]:
        """Synchronous Twitter fetch."""
        client = self._get_twitter_client()
        if not client:
            return {"score": 0.0, "count": 0, "posts": [], "themes": []}

        import tweepy
        query = f"${symbol} OR #{symbol} -is:retweet lang:en"
        try:
            response = client.search_recent_tweets(
                query=query,
                max_results=100,
                tweet_fields=["created_at", "public_metrics", "author_id"],
            )
        except tweepy.TooManyRequests:
            logger.warning("Twitter rate limit hit", symbol=symbol)
            return {"score": 0.0, "count": 0, "posts": [], "themes": []}
        except Exception as e:
            raise e

        if not response.data:
            return {"score": 0.0, "count": 0, "posts": [], "themes": []}

        scores = []
        posts = []
        all_words: List[str] = []

        for tweet in response.data:
            text = tweet.text
            score = _score_text(text)
            scores.append(score)
            metrics = tweet.public_metrics or {}
            engagement = (
                metrics.get("like_count", 0) * 2 +
                metrics.get("retweet_count", 0) * 3 +
                metrics.get("reply_count", 0)
            )
            posts.append({
                "platform": "twitter",
                "text": text[:200],
                "score": score,
                "engagement": engagement,
                "created_at": str(tweet.created_at) if hasattr(tweet, "created_at") else None,
            })
            words = re.findall(r'\b[A-Za-z]{4,}\b', text.lower())
            all_words.extend(words)

        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Extract common themes
        from collections import Counter
        stop_words = {"that", "this", "with", "from", "have", "will", "been", "they", "their", "just"}
        word_freq = Counter(w for w in all_words if w not in stop_words)
        themes = [word for word, _ in word_freq.most_common(5)]

        # Sort posts by engagement
        posts.sort(key=lambda x: x["engagement"], reverse=True)

        return {
            "score": avg_score,
            "count": len(response.data),
            "posts": posts[:5],
            "themes": themes,
        }

    async def _get_reddit_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Fetch and score Reddit posts about the symbol."""
        if not self._reddit_enabled:
            return {"score": 0.0, "count": 0, "posts": [], "themes": []}

        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._fetch_reddit_sync(symbol)
            )
        except Exception as e:
            logger.warning("Reddit sentiment failed", symbol=symbol, error=str(e))
            return {"score": 0.0, "count": 0, "posts": [], "themes": []}

    def _fetch_reddit_sync(self, symbol: str) -> Dict[str, Any]:
        """Synchronous Reddit fetch."""
        reddit = self._get_reddit_client()
        if not reddit:
            return {"score": 0.0, "count": 0, "posts": [], "themes": []}

        subreddits = [
            "investing", "wallstreetbets", "stocks", "StockMarket",
            "options", "IsraeliFinance", "SecurityAnalysis"
        ]

        scores = []
        posts = []
        all_words: List[str] = []
        total_count = 0

        for sub_name in subreddits[:5]:  # Limit to avoid rate limits
            try:
                subreddit = reddit.subreddit(sub_name)
                search_results = subreddit.search(
                    f"{symbol}",
                    sort="new",
                    time_filter="week",
                    limit=20,
                )
                for post in search_results:
                    text = (post.title or "") + " " + (post.selftext or "")[:500]
                    score = _score_text(text)
                    scores.append(score)
                    total_count += 1
                    posts.append({
                        "platform": "reddit",
                        "subreddit": sub_name,
                        "title": post.title[:200],
                        "text": (post.selftext or "")[:200],
                        "score": score,
                        "upvotes": post.score,
                        "comments": post.num_comments,
                        "created_at": datetime.fromtimestamp(
                            post.created_utc, tz=timezone.utc
                        ).isoformat(),
                        "url": f"https://reddit.com{post.permalink}",
                    })
                    words = re.findall(r'\b[A-Za-z]{4,}\b', text.lower())
                    all_words.extend(words)
            except Exception as e:
                logger.debug("Reddit subreddit search failed", subreddit=sub_name, error=str(e))
                continue

        if not scores:
            return {"score": 0.0, "count": 0, "posts": [], "themes": []}

        avg_score = sum(scores) / len(scores)

        from collections import Counter
        stop_words = {"that", "this", "with", "from", "have", "will", "been", "they", "their"}
        word_freq = Counter(w for w in all_words if w not in stop_words)
        themes = [word for word, _ in word_freq.most_common(5)]

        # Sort by engagement (upvotes)
        posts.sort(key=lambda x: x.get("upvotes", 0), reverse=True)

        return {
            "score": avg_score,
            "count": total_count,
            "posts": posts[:5],
            "themes": themes,
        }
