"""
Social Sentiment Service
Aggregates sentiment from Twitter/X and Reddit.
Calculates a composite sentiment score from -1 (very bearish) to +1 (very bullish).
"""
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
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


# ─── Grok spend controls ─────────────────────────────────────────────────────
# xAI bills x_search per live search, and the watcher jobs ask about the same
# symbols every 30 minutes. Without a cache that is ~48 paid searches per symbol
# per day for information that barely changes; with one it is ~4.
_GROK_CACHE_KEY = "investment_ai:grok_x:"        # + symbol
_GROK_COUNT_KEY = "investment_ai:grok_calls:"    # + YYYY-MM-DD
_GROK_COUNT_TTL = 60 * 60 * 30


async def _grok_redis():
    import redis.asyncio as aioredis
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def grok_calls_today() -> int:
    """How many paid Grok searches were made today."""
    try:
        r = await _grok_redis()
        try:
            val = await r.get(_GROK_COUNT_KEY + datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        finally:
            await r.aclose()
        return int(val or 0)
    except Exception:
        return 0


async def grok_limit_reached() -> bool:
    limit = int(getattr(settings, "DAILY_GROK_CALL_LIMIT", 0) or 0)
    if limit <= 0:
        return False
    return await grok_calls_today() >= limit


async def _grok_record_call() -> int:
    try:
        r = await _grok_redis()
        try:
            key = _GROK_COUNT_KEY + datetime.now(timezone.utc).strftime("%Y-%m-%d")
            n = await r.incr(key)
            await r.expire(key, _GROK_COUNT_TTL)
            return int(n)
        finally:
            await r.aclose()
    except Exception:
        return 0


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
            self._get_stocktwits_sentiment(symbol),
            self._get_grok_x_sentiment(symbol),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        _empty = {"score": 0.0, "count": 0, "posts": [], "themes": []}
        twitter_result = results[0] if not isinstance(results[0], Exception) else dict(_empty)
        reddit_result = results[1] if not isinstance(results[1], Exception) else dict(_empty)
        stocktwits_result = results[2] if not isinstance(results[2], Exception) else dict(_empty)
        grok_result = results[3] if not isinstance(results[3], Exception) else dict(_empty)

        twitter_score = twitter_result.get("score", 0.0)
        twitter_count = twitter_result.get("count", 0)
        reddit_score = reddit_result.get("score", 0.0)
        reddit_count = reddit_result.get("count", 0)
        stocktwits_score = stocktwits_result.get("score", 0.0)
        stocktwits_count = stocktwits_result.get("count", 0)
        grok_score = grok_result.get("score", 0.0)
        # Grok reports an estimated X post volume; cap it so a huge estimate
        # can't swamp the mention total / composite weighting.
        grok_count = min(int(grok_result.get("count", 0) or 0), 100)

        total_count = twitter_count + reddit_count + stocktwits_count + grok_count

        # Weighted composite: Grok reads live X with real reasoning (highest),
        # Stocktwits is finance-native with explicit bull/bear labels, Reddit has
        # depth, Twitter (legacy direct API) is usually off.
        if total_count > 0:
            composite_score = (
                twitter_score * twitter_count * 0.20
                + reddit_score * reddit_count * 0.25
                + stocktwits_score * stocktwits_count * 0.25
                + grok_score * grok_count * 0.30
            ) / max(total_count, 1)
        else:
            composite_score = 0.0

        # Clamp to [-1, 1]
        composite_score = max(-1.0, min(1.0, composite_score))

        # Trending: more than 100 mentions in last 24h
        is_trending = total_count > 100

        # Combine top posts
        all_posts = (
            twitter_result.get("posts", [])[:2]
            + reddit_result.get("posts", [])[:2]
            + stocktwits_result.get("posts", [])[:2]
            + grok_result.get("posts", [])[:2]
        )

        # Combine themes
        all_themes = list(set(
            twitter_result.get("themes", [])
            + reddit_result.get("themes", [])
            + stocktwits_result.get("themes", [])
            + grok_result.get("themes", [])
        ))[:10]

        return SocialSentiment(
            score=round(composite_score, 4),
            mentions=total_count,
            trending=is_trending,
            top_posts=all_posts[:8],
            key_themes=all_themes,
            twitter_score=round(twitter_score, 4),
            reddit_score=round(reddit_score, 4),
            stocktwits_score=round(stocktwits_score, 4),
            grok_x_score=round(grok_score, 4),
            tweet_count=twitter_count,
            reddit_post_count=reddit_count,
            stocktwits_post_count=stocktwits_count,
            grok_x_post_count=grok_count,
        )

    @staticmethod
    def _extract_responses_text(payload: Dict[str, Any]) -> str:
        """Pull the final assistant text out of an xAI /v1/responses payload.
        Tolerates the convenience `output_text` field or the nested
        output[].content[].text structure."""
        if not isinstance(payload, dict):
            return ""
        # Convenience field (present on many responses)
        txt = payload.get("output_text")
        if isinstance(txt, str) and txt.strip():
            return txt
        parts: List[str] = []
        for item in payload.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for c in item.get("content", []) or []:
                    if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                        t = c.get("text")
                        if isinstance(t, str):
                            parts.append(t)
        return "\n".join(parts)

    async def _get_grok_x_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Sentiment from X (Twitter) via xAI Grok's live search — Grok is the only
        frontier model grounded on real-time X posts, so this replaces the paid
        X API. Grok reads recent posts and returns a reasoned sentiment read.
        Graceful: returns empty (with error detail) if XAI_API_KEY is unset or
        the call fails. .TA symbols are skipped (little Hebrew X coverage).
        """
        empty = {"score": 0.0, "count": 0, "posts": [], "themes": []}
        api_key = (settings.XAI_API_KEY or "").strip()
        if not api_key:
            return empty
        if symbol.endswith(".TA"):
            return empty

        # Serve from cache before spending a search. Callers run every 30 min on
        # the same symbols; X sentiment does not turn over that fast.
        cache_key = _GROK_CACHE_KEY + symbol
        try:
            r = await _grok_redis()
            try:
                cached = await r.get(cache_key)
            finally:
                await r.aclose()
            if cached:
                data = json.loads(cached)
                data["cached"] = True
                return data
        except Exception:
            pass

        if await grok_limit_reached():
            logger.warning(
                "Grok daily call limit reached — skipping X sentiment",
                symbol=symbol, limit=settings.DAILY_GROK_CALL_LIMIT,
            )
            return {**empty, "error": "daily Grok call limit reached"}

        model = re.sub(r"[^A-Za-z0-9._\-/]", "", settings.XAI_MODEL or "") or "grok-4-fast"
        from_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
        prompt = (
            f"Search X (Twitter) for recent posts about the stock ${symbol}. "
            "Assess the aggregate sentiment of traders and investors based on the real posts you find. "
            "Respond with ONLY strict JSON, no prose:\n"
            '{"score": <float from -1 (very bearish) to 1 (very bullish)>, '
            '"post_count": <int estimate of relevant posts found>, '
            '"summary": "<one concise sentence>", '
            '"themes": ["<short theme>", "<short theme>"]}'
        )
        await _grok_record_call()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
                # New Agent Tools API (/v1/responses) — the old search_parameters
                # live-search was deprecated (HTTP 410). Grok invokes x_search
                # server-side and returns a final message.
                resp = await client.post(
                    "https://api.x.ai/v1/responses",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "input": [{"role": "user", "content": prompt}],
                        "tools": [{"type": "x_search", "from_date": from_date}],
                    },
                )
                if resp.status_code != 200:
                    logger.debug("Grok non-200", symbol=symbol, status=resp.status_code, body=resp.text[:200])
                    return {**empty, "error": f"xAI {resp.status_code}: {resp.text[:140]}"}
                content = self._extract_responses_text(resp.json())

            if not content:
                return {**empty, "error": "empty response from xAI"}
            if "```" in content:
                content = content.split("```")[1]
                if content.lstrip().lower().startswith("json"):
                    content = content.lstrip()[4:]
            # Grok may wrap JSON in surrounding text — grab the first {...} block
            start, end = content.find("{"), content.rfind("}")
            if start != -1 and end != -1:
                content = content[start:end + 1]
            data = json.loads(content.strip())

            score = float(data.get("score", 0.0))
            count = int(data.get("post_count", 0) or 0)
            summary = str(data.get("summary", ""))[:200]
            themes = [str(t)[:40] for t in (data.get("themes") or [])][:5]
            posts = [{"platform": "x_grok", "text": summary, "score": score}] if summary else []
            result = {
                "score": round(max(-1.0, min(1.0, score)), 4),
                "count": count,
                "posts": posts,
                "themes": themes,
            }
            try:
                ttl = max(60, int(getattr(settings, "GROK_CACHE_TTL_MIN", 360)) * 60)
                r = await _grok_redis()
                try:
                    await r.set(cache_key, json.dumps(result), ex=ttl)
                finally:
                    await r.aclose()
            except Exception:
                pass
            return result
        except Exception as e:
            logger.debug("Grok X sentiment failed", symbol=symbol, error=str(e))
            return {**empty, "error": str(e)[:120]}

    async def _get_stocktwits_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch sentiment from Stocktwits — a finance-native social network.
        Free public endpoint, no API key required. Messages carry explicit
        Bullish/Bearish labels set by their authors, which beats text scoring.
        TASE symbols (.TA) are not covered — returns empty for them.
        """
        empty = {"score": 0.0, "count": 0, "posts": [], "themes": []}
        if symbol.endswith(".TA"):
            return empty
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(
                    f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json",
                    headers={"User-Agent": "Mozilla/5.0 (compatible; InvestmentAI/1.0)"},
                )
                if resp.status_code != 200:
                    logger.debug("Stocktwits non-200", symbol=symbol, status=resp.status_code)
                    return empty
                messages = (resp.json() or {}).get("messages") or []

            bullish = bearish = 0
            posts = []
            for msg in messages:
                label = (((msg.get("entities") or {}).get("sentiment") or {}) or {}).get("basic", "")
                body = msg.get("body", "")
                if label == "Bullish":
                    bullish += 1
                elif label == "Bearish":
                    bearish += 1
                if len(posts) < 3 and body:
                    posts.append({
                        "platform": "stocktwits",
                        "text": body[:200],
                        "score": 1.0 if label == "Bullish" else -1.0 if label == "Bearish" else _score_text(body),
                    })

            labeled = bullish + bearish
            # Prefer explicit author labels; fall back to keyword scoring
            if labeled > 0:
                score = (bullish - bearish) / labeled
            elif messages:
                score = sum(_score_text(m.get("body", "")) for m in messages) / len(messages)
            else:
                return empty

            return {
                "score": round(max(-1.0, min(1.0, score)), 4),
                "count": len(messages),
                "posts": posts,
                "themes": [],
            }
        except Exception as e:
            logger.debug("Stocktwits fetch failed", symbol=symbol, error=str(e))
            return empty

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
