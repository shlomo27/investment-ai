"""
Data Fetcher Agent - הפקיד (The Clerk)
Responsible for gathering all raw market data, news, and social sentiment
before passing to the Fundamental Analyst.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog

from langchain_anthropic import ChatAnthropic
from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.agents.state import MarketDataState, NewsItem, SocialSentiment, EarningsData
from app.services.market_data.yahoo_service import YahooFinanceService
from app.services.market_data.tase_service import TASEService
from app.services.market_data.sentiment_service import SentimentService
from app.services.market_data.news_service import NewsService
from app.services.market_data.fmp_service import get_fmp_service
from app.services.market_data.alpaca_service import get_alpaca_service

logger = structlog.get_logger(__name__)


class DataFetcherAgent:
    """
    הפקיד - The Clerk Agent
    Gathers all raw market data from multiple sources in parallel.
    """

    def __init__(self):
        self._llm = None
        self.yahoo_service = YahooFinanceService()
        self.tase_service = TASEService()
        self.sentiment_service = SentimentService()
        self.news_service = NewsService()

    def _get_llm(self):
        """Lazy-initialize the LLM only when first needed."""
        if not settings.ANTHROPIC_API_KEY:
            return None
        if self._llm is None:
            self._llm = ChatAnthropic(
                model=settings.CLAUDE_MODEL,
                api_key=settings.ANTHROPIC_API_KEY,
                max_tokens=settings.CLAUDE_MAX_TOKENS,
                temperature=0.1,
            )
        return self._llm

    async def fetch_all_data(self, symbol: str, exchange: str) -> MarketDataState:
        """
        Main entry point. Fetches all data sources in parallel.
        Returns a comprehensive MarketDataState.
        """
        logger.info("DataFetcherAgent starting", symbol=symbol, exchange=exchange)
        fetch_errors: List[str] = []

        # Run all fetches in parallel
        is_tase = exchange == "TASE"

        tasks = [
            self._fetch_price_and_fundamentals(symbol, is_tase),
            self.sentiment_service.get_sentiment(symbol),
            self.news_service.get_news(symbol),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        price_data, sentiment_result, news_result = results

        # Handle price/fundamentals
        if isinstance(price_data, Exception):
            logger.error("Price data fetch failed", symbol=symbol, error=str(price_data))
            fetch_errors.append(f"Price data: {str(price_data)}")
            price_data = self._empty_price_data(symbol, exchange)

        # Handle sentiment
        if isinstance(sentiment_result, Exception):
            logger.warning("Sentiment fetch failed", symbol=symbol, error=str(sentiment_result))
            fetch_errors.append(f"Sentiment: {str(sentiment_result)}")
            sentiment_result = self._empty_sentiment()

        # Handle news
        if isinstance(news_result, Exception):
            logger.warning("News fetch failed", symbol=symbol, error=str(news_result))
            fetch_errors.append(f"News: {str(news_result)}")
            news_result = []

        # Use Claude to summarize and validate the raw data
        summarized_context = await self._summarize_with_claude(
            symbol=symbol,
            price_data=price_data,
            sentiment=sentiment_result,
            news_items=news_result,
            fetch_errors=fetch_errors,
        )

        state: MarketDataState = {
            "symbol": symbol,
            "exchange": exchange,
            "price": price_data.get("price", 0.0),
            "previous_close": price_data.get("previous_close", 0.0),
            "volume": price_data.get("volume", 0),
            "avg_volume_30d": price_data.get("avg_volume_30d", 0),
            "market_cap": price_data.get("market_cap", 0.0),
            "pe_ratio": price_data.get("pe_ratio"),
            "forward_pe": price_data.get("forward_pe"),
            "peg_ratio": price_data.get("peg_ratio"),
            "price_to_book": price_data.get("price_to_book"),
            "price_to_sales": price_data.get("price_to_sales"),
            "debt_to_equity": price_data.get("debt_to_equity"),
            "current_ratio": price_data.get("current_ratio"),
            "quick_ratio": price_data.get("quick_ratio"),
            "revenue_growth": price_data.get("revenue_growth"),
            "earnings_growth": price_data.get("earnings_growth"),
            "profit_margin": price_data.get("profit_margin"),
            "operating_margin": price_data.get("operating_margin"),
            "roe": price_data.get("roe"),
            "roa": price_data.get("roa"),
            "free_cash_flow": price_data.get("free_cash_flow"),
            "dividend_yield": price_data.get("dividend_yield"),
            "beta": price_data.get("beta"),
            "fifty_two_week_high": price_data.get("fifty_two_week_high", 0.0),
            "fifty_two_week_low": price_data.get("fifty_two_week_low", 0.0),
            "earnings_data": price_data.get("earnings_data"),
            "news_items": news_result,
            "social_sentiment": sentiment_result,
            "technical_indicators": None,  # Fetched on-demand by TechnicalAgent
            "sector": price_data.get("sector"),
            "industry": price_data.get("industry"),
            "country": price_data.get("country", "US"),
            "currency": price_data.get("currency", "USD"),
            "company_description": summarized_context.get("company_summary"),
            "analyst_target_price": price_data.get("analyst_target_price"),
            "analyst_recommendation": price_data.get("analyst_recommendation"),
            "institutional_ownership": price_data.get("institutional_ownership"),
            "short_interest": price_data.get("short_interest"),
            "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
            "fetch_errors": fetch_errors,
        }

        logger.info(
            "DataFetcherAgent completed",
            symbol=symbol,
            price=state["price"],
            sentiment_score=state["social_sentiment"]["score"],
            news_count=len(state["news_items"]),
            errors=len(fetch_errors),
        )

        return state

    async def _fetch_price_and_fundamentals(self, symbol: str, is_tase: bool) -> Dict[str, Any]:
        """
        Fetch price data and fundamentals.
        Priority for US stocks: Yahoo Finance → Alpaca (price only) → FMP
        """
        if is_tase:
            return await self.tase_service.get_tase_stock_info(symbol)

        # Primary: Yahoo Finance
        result = await self.yahoo_service.get_stock_info(symbol)
        if result and result.get("price", 0) > 0:
            return result

        logger.warning("Yahoo Finance returned no price — trying Alpaca snapshot", symbol=symbol)

        # Fallback 1: Alpaca (price/volume only, fast)
        alpaca = get_alpaca_service()
        snap = await alpaca.get_snapshot(symbol)
        if snap and snap.get("price", 0) > 0:
            logger.info("Alpaca snapshot succeeded", symbol=symbol, price=snap["price"])
            # Merge Alpaca price into Yahoo result (which has fundamentals even if price=0)
            base = result or self._empty_price_data(symbol, "US")
            base.update({
                "price":          snap["price"],
                "previous_close": snap.get("previous_close", 0),
                "volume":         snap.get("volume", 0),
            })
            return base

        logger.warning("Alpaca unavailable — trying FMP", symbol=symbol)

        # Fallback 2: FMP (full fundamentals)
        fmp_result = await get_fmp_service().get_stock_info(symbol)
        if fmp_result and fmp_result.get("price", 0) > 0:
            logger.info("FMP fallback succeeded", symbol=symbol, price=fmp_result["price"])
            return fmp_result

        logger.error(
            "All market data sources failed — returning empty data. "
            "Analysis will use Claude training knowledge only.",
            symbol=symbol,
        )
        return result or self._empty_price_data(symbol, "US")

    async def _summarize_with_claude(
        self,
        symbol: str,
        price_data: Dict[str, Any],
        sentiment: SocialSentiment,
        news_items: List[NewsItem],
        fetch_errors: List[str],
    ) -> Dict[str, Any]:
        """Use Claude to create a brief structured summary of the raw data."""
        llm = self._get_llm()
        if llm is None:
            logger.warning("Claude LLM unavailable (missing API key), skipping summarization", symbol=symbol)
            return {
                "company_summary": f"Market data collected for {symbol}.",
                "data_quality_issues": [],
                "exceptional_signals": [],
                "data_completeness_score": 50,
            }

        try:
            news_text = "\n".join([
                f"- {n['title']} ({n['source']}): sentiment={n.get('sentiment', 0):.2f}"
                for n in news_items[:5]
            ])

            prompt = f"""You are הפקיד (The Clerk), a data gathering AI agent for an investment platform.

You have just collected raw market data for {symbol}. Your job is to:
1. Provide a brief 2-3 sentence company summary
2. Flag any data quality issues or inconsistencies
3. Note any exceptional signals (e.g., extreme sentiment, missing critical data)

Raw Data Summary:
- Price: {price_data.get('price', 'N/A')}
- Market Cap: {price_data.get('market_cap', 'N/A')}
- P/E Ratio: {price_data.get('pe_ratio', 'N/A')}
- Revenue Growth: {price_data.get('revenue_growth', 'N/A')}
- Sentiment Score: {sentiment.get('score', 0):.2f} (from {sentiment.get('mentions', 0)} mentions)
- Trending: {sentiment.get('trending', False)}
- News Count: {len(news_items)}
Recent News:
{news_text if news_text else 'No news available'}
- Fetch Errors: {fetch_errors if fetch_errors else 'None'}

Respond in JSON format:
{{
  "company_summary": "...",
  "data_quality_issues": [...],
  "exceptional_signals": [...],
  "data_completeness_score": 0-100
}}"""

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content="You are a financial data aggregation AI. Respond only in valid JSON."),
                    HumanMessage(content=prompt)
                ])
            )

            content = response.content
            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return json.loads(content)

        except Exception as e:
            logger.warning("Claude summarization failed", symbol=symbol, error=str(e))
            return {
                "company_summary": f"Market data collected for {symbol}.",
                "data_quality_issues": [],
                "exceptional_signals": [],
                "data_completeness_score": 50,
            }

    def _empty_price_data(self, symbol: str, exchange: str) -> Dict[str, Any]:
        return {
            "price": 0.0,
            "previous_close": 0.0,
            "volume": 0,
            "avg_volume_30d": 0,
            "market_cap": 0.0,
            "country": "IL" if exchange == "TASE" else "US",
            "currency": "ILS" if exchange == "TASE" else "USD",
            "fifty_two_week_high": 0.0,
            "fifty_two_week_low": 0.0,
        }

    def _empty_sentiment(self) -> SocialSentiment:
        return {
            "score": 0.0,
            "mentions": 0,
            "trending": False,
            "top_posts": [],
            "key_themes": [],
            "twitter_score": 0.0,
            "reddit_score": 0.0,
            "tweet_count": 0,
            "reddit_post_count": 0,
        }


# Singleton instance
_data_fetcher_agent: Optional[DataFetcherAgent] = None


def get_data_fetcher_agent() -> DataFetcherAgent:
    global _data_fetcher_agent
    if _data_fetcher_agent is None:
        _data_fetcher_agent = DataFetcherAgent()
    return _data_fetcher_agent
