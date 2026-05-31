"""
News Analyst Agent — GPT
Deep NLP analysis of news items using OpenAI GPT.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.agents.state import MarketDataState

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a financial news analyst specializing in market-moving events.
For a given stock's news items, you will:
1. Classify each event by type: EARNINGS, PRODUCT_LAUNCH, LEGAL, REGULATORY, MACRO, ANALYST_CHANGE, MERGER_ACQUISITION, MANAGEMENT_CHANGE, OTHER
2. Identify key entities (people, companies, products, regulations)
3. Detect hidden signals a basic sentiment score might miss
4. Assess market impact (HIGH/MEDIUM/LOW) and direction (POSITIVE/NEGATIVE/NEUTRAL)
5. Flag anomalies (conflicting signals, unusual negative volume)
6. Identify the dominant narrative across all news
Output must be strict JSON."""


class NewsAnalystAgent:
    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if not settings.OPENAI_API_KEY:
            return None
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                api_key=settings.OPENAI_API_KEY,
                max_tokens=1500,
                temperature=0.1,
            )
        return self._llm

    async def analyze(self, market_data: MarketDataState) -> Dict[str, Any]:
        symbol = market_data["symbol"]
        news_items = market_data.get("news_items") or []
        sentiment = market_data.get("social_sentiment") or {}

        logger.info("NewsAnalystAgent starting", symbol=symbol, news_count=len(news_items))

        llm = self._get_llm()
        if llm is None:
            logger.warning("OpenAI unavailable, skipping news analysis", symbol=symbol)
            return self._empty_analysis(symbol, "OPENAI_API_KEY not configured")

        if not news_items:
            return self._empty_analysis(symbol, "No news items to analyze")

        prompt = self._build_prompt(symbol, news_items, sentiment)

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ])
            )
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)
            result["symbol"] = symbol
            result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
            result["news_count"] = len(news_items)

            logger.info(
                "NewsAnalystAgent completed",
                symbol=symbol,
                impact=result.get("overall_market_impact"),
                direction=result.get("overall_direction"),
            )
            return result

        except json.JSONDecodeError as e:
            logger.error("JSON parse error in news analysis", error=str(e))
            return self._empty_analysis(symbol, f"JSON parse error: {e}")
        except Exception as e:
            logger.error("News analysis failed", symbol=symbol, error=str(e))
            return self._empty_analysis(symbol, str(e))

    def _build_prompt(self, symbol: str, news_items: List[Dict], sentiment: Dict) -> str:
        news_text = "\n".join([
            f"{i+1}. [{n.get('source', '?')}] {n.get('title', '')} (sentiment: {n.get('sentiment', 0):+.2f})"
            for i, n in enumerate(news_items[:15])
        ])
        return f"""Analyze the following news items for {symbol}:

Social Sentiment Score: {sentiment.get('score', 0):.3f}
Key Social Themes: {', '.join((sentiment.get('key_themes') or [])[:5])}

NEWS ITEMS:
{news_text}

Respond ONLY with valid JSON:
{{
  "dominant_narrative": "<1-2 sentences on the main story driving the stock>",
  "event_classifications": [
    {{"title": "<shortened title>", "type": "<event type>", "impact": "HIGH|MEDIUM|LOW", "direction": "POSITIVE|NEGATIVE|NEUTRAL"}}
  ],
  "key_entities": ["<entity1>", "<entity2>"],
  "hidden_signals": ["<signal not captured by basic sentiment>"],
  "overall_market_impact": "HIGH|MEDIUM|LOW",
  "overall_direction": "POSITIVE|NEGATIVE|NEUTRAL",
  "sentiment_news_alignment": "ALIGNED|DIVERGENT|NEUTRAL",
  "red_flags": ["<flag1>"],
  "opportunities": ["<opportunity1>"],
  "news_quality_score": 0-100
}}"""

    def _empty_analysis(self, symbol: str, reason: str) -> Dict[str, Any]:
        return {
            "dominant_narrative": "News analysis unavailable",
            "event_classifications": [],
            "key_entities": [],
            "hidden_signals": [],
            "overall_market_impact": "LOW",
            "overall_direction": "NEUTRAL",
            "sentiment_news_alignment": "NEUTRAL",
            "red_flags": [],
            "opportunities": [],
            "news_quality_score": 0,
            "symbol": symbol,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "news_count": 0,
            "skipped_reason": reason,
        }


_news_agent: Optional[NewsAnalystAgent] = None


def get_news_agent() -> NewsAnalystAgent:
    global _news_agent
    if _news_agent is None:
        _news_agent = NewsAnalystAgent()
    return _news_agent
