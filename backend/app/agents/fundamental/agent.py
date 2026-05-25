"""
Fundamental Analyst Agent
Performs deep fundamental analysis on market data collected by הפקיד.
Uses Claude claude-sonnet-4-6 to reason about P/E, earnings quality, sector comparison, etc.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.agents.state import MarketDataState

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a senior fundamental analyst at an elite investment firm.
You analyze stocks with rigorous financial discipline. Your job is to:
1. Evaluate key financial ratios (P/E, PEG, P/B, P/S, debt ratios)
2. Assess earnings quality and revenue growth sustainability
3. Analyze free cash flow generation ability
4. Compare against sector benchmarks
5. Cross-reference financial health with social sentiment
6. Identify key risks and opportunities
7. Provide a clear recommendation with confidence level

You always think in terms of risk-adjusted returns and portfolio construction.
Your output must be structured JSON. Be precise and data-driven.
Do not make recommendations based on sentiment alone - fundamentals must justify the trade."""


class FundamentalAnalystAgent:
    """
    The Fundamental Analyst Agent.
    Receives raw MarketDataState from DataFetcherAgent and produces investment analysis.
    """

    def __init__(self):
        self.llm = ChatAnthropic(
            model=settings.CLAUDE_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
            temperature=0.2,
        )

    async def analyze(
        self,
        market_data: MarketDataState,
        portfolio_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main analysis method. Returns structured fundamental analysis dict.
        """
        logger.info(
            "FundamentalAnalystAgent starting analysis",
            symbol=market_data["symbol"],
            price=market_data.get("price"),
        )

        prompt = self._build_analysis_prompt(market_data, portfolio_context)

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.llm.invoke([
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=prompt)
                ])
            )

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            analysis = json.loads(content)

            # Validate required fields
            analysis = self._validate_and_normalize(analysis, market_data)

            logger.info(
                "FundamentalAnalystAgent completed",
                symbol=market_data["symbol"],
                recommendation=analysis.get("recommendation_type"),
                confidence=analysis.get("confidence_score"),
            )

            return analysis

        except json.JSONDecodeError as e:
            logger.error("JSON parse error in fundamental analysis", error=str(e))
            return self._fallback_analysis(market_data, f"JSON parse error: {e}")
        except Exception as e:
            logger.error("Fundamental analysis failed", symbol=market_data["symbol"], error=str(e))
            return self._fallback_analysis(market_data, str(e))

    def _build_analysis_prompt(
        self,
        data: MarketDataState,
        portfolio_context: Optional[Dict[str, Any]],
    ) -> str:
        news_summary = "\n".join([
            f"  - [{n.get('sentiment', 0):+.2f}] {n['title']} ({n['source']})"
            for n in data.get("news_items", [])[:8]
        ])

        sentiment = data.get("social_sentiment", {})
        earnings = data.get("earnings_data") or {}

        portfolio_section = ""
        if portfolio_context:
            portfolio_section = f"""
PORTFOLIO CONTEXT:
- Total Portfolio Value: ${portfolio_context.get('total_value', 0):,.2f}
- Available Cash: ${portfolio_context.get('cash_balance', 0):,.2f}
- Current Holdings: {portfolio_context.get('holdings_count', 0)} positions
- Max Single Asset Exposure: {portfolio_context.get('max_exposure_pct', 3)}%
- Existing Position in {data['symbol']}: {portfolio_context.get('existing_position', 'None')}
"""

        prompt = f"""Perform comprehensive fundamental analysis for {data['symbol']} ({data['exchange']}).

=== MARKET DATA ===
Current Price: {data.get('price', 'N/A')} {data.get('currency', 'USD')}
Previous Close: {data.get('previous_close', 'N/A')}
52-Week Range: {data.get('fifty_two_week_low', 'N/A')} - {data.get('fifty_two_week_high', 'N/A')}
Volume: {data.get('volume', 'N/A'):,} (30d avg: {data.get('avg_volume_30d', 'N/A'):,})
Market Cap: ${data.get('market_cap', 0):,.0f}
Sector: {data.get('sector', 'Unknown')} | Industry: {data.get('industry', 'Unknown')}
Country: {data.get('country', 'US')}

=== VALUATION RATIOS ===
P/E Ratio (TTM): {data.get('pe_ratio', 'N/A')}
Forward P/E: {data.get('forward_pe', 'N/A')}
PEG Ratio: {data.get('peg_ratio', 'N/A')}
Price/Book: {data.get('price_to_book', 'N/A')}
Price/Sales: {data.get('price_to_sales', 'N/A')}
Analyst Target: {data.get('analyst_target_price', 'N/A')} | Analyst Rec: {data.get('analyst_recommendation', 'N/A')}

=== FINANCIAL HEALTH ===
Revenue Growth (YoY): {data.get('revenue_growth', 'N/A')}
Earnings Growth (YoY): {data.get('earnings_growth', 'N/A')}
Profit Margin: {data.get('profit_margin', 'N/A')}
Operating Margin: {data.get('operating_margin', 'N/A')}
ROE: {data.get('roe', 'N/A')}
ROA: {data.get('roa', 'N/A')}
Free Cash Flow: ${data.get('free_cash_flow', 0):,.0f}
Debt/Equity: {data.get('debt_to_equity', 'N/A')}
Current Ratio: {data.get('current_ratio', 'N/A')}
Quick Ratio: {data.get('quick_ratio', 'N/A')}
Beta: {data.get('beta', 'N/A')}
Dividend Yield: {data.get('dividend_yield', 'N/A')}
Institutional Ownership: {data.get('institutional_ownership', 'N/A')}
Short Interest: {data.get('short_interest', 'N/A')}

=== EARNINGS ===
Last EPS: {earnings.get('last_eps', 'N/A')} (Estimate: {earnings.get('eps_estimate', 'N/A')}, Surprise: {earnings.get('eps_surprise_pct', 'N/A')}%)
Revenue Last: ${earnings.get('revenue_last', 0):,.0f} (Estimate: ${earnings.get('revenue_estimate', 0):,.0f})
Next Earnings Date: {earnings.get('earnings_date', 'N/A')}

=== SOCIAL SENTIMENT ===
Overall Sentiment Score: {sentiment.get('score', 0):.3f} (-1 bearish to +1 bullish)
Total Mentions: {sentiment.get('mentions', 0):,}
Twitter Score: {sentiment.get('twitter_score', 0):.3f} ({sentiment.get('tweet_count', 0)} tweets)
Reddit Score: {sentiment.get('reddit_score', 0):.3f} ({sentiment.get('reddit_post_count', 0)} posts)
Trending: {sentiment.get('trending', False)}
Key Themes: {', '.join(sentiment.get('key_themes', [])[:5])}

=== RECENT NEWS ===
{news_summary if news_summary else 'No recent news available'}
{portfolio_section}
=== COMPANY CONTEXT ===
{data.get('company_description', 'No description available.')}

---

Based on ALL the above data, provide your fundamental analysis in this exact JSON format:
{{
  "recommendation_type": "BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL",
  "confidence_score": 0-100,
  "target_price": <float or null>,
  "stop_loss": <float or null>,
  "expected_return_pct": <float or null>,
  "investment_horizon": "SHORT_TERM|MEDIUM_TERM|LONG_TERM",
  "valuation_assessment": "UNDERVALUED|FAIRLY_VALUED|OVERVALUED",
  "financial_health": "EXCELLENT|GOOD|FAIR|POOR",
  "key_metrics_summary": {{
    "pe_assessment": "<text>",
    "growth_quality": "<text>",
    "balance_sheet_strength": "<text>",
    "cash_flow_quality": "<text>",
    "sentiment_alignment": "<text>"
  }},
  "bull_case": "<2-3 sentences>",
  "bear_case": "<2-3 sentences>",
  "risk_factors": ["<risk1>", "<risk2>", ...],
  "catalysts": ["<catalyst1>", "<catalyst2>", ...],
  "sector_comparison": "<text>",
  "sentiment_cross_check": "<text explaining if sentiment aligns with fundamentals>",
  "analyst_notes": "<detailed analysis notes>",
  "data_completeness": 0-100
}}"""

        return prompt

    def _validate_and_normalize(
        self,
        analysis: Dict[str, Any],
        data: MarketDataState,
    ) -> Dict[str, Any]:
        """Ensure all required fields exist with valid values."""
        valid_rec_types = {"BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"}

        if analysis.get("recommendation_type") not in valid_rec_types:
            analysis["recommendation_type"] = "HOLD"

        confidence = analysis.get("confidence_score", 50)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 100:
            analysis["confidence_score"] = 50.0
        else:
            analysis["confidence_score"] = float(confidence)

        # Add metadata
        analysis["symbol"] = data["symbol"]
        analysis["analysis_timestamp"] = datetime.now(timezone.utc).isoformat()
        analysis["analyst_id"] = "fundamental_agent_v1"

        return analysis

    def _fallback_analysis(self, data: MarketDataState, error: str) -> Dict[str, Any]:
        """Return a safe fallback analysis when Claude fails."""
        return {
            "recommendation_type": "HOLD",
            "confidence_score": 0.0,
            "target_price": None,
            "stop_loss": None,
            "expected_return_pct": None,
            "investment_horizon": "MEDIUM_TERM",
            "valuation_assessment": "FAIRLY_VALUED",
            "financial_health": "FAIR",
            "key_metrics_summary": {},
            "bull_case": "Analysis unavailable due to system error.",
            "bear_case": "Analysis unavailable due to system error.",
            "risk_factors": ["Analysis system error"],
            "catalysts": [],
            "sector_comparison": "N/A",
            "sentiment_cross_check": "N/A",
            "analyst_notes": f"Analysis failed: {error}",
            "data_completeness": 0,
            "symbol": data["symbol"],
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "analyst_id": "fundamental_agent_v1",
            "error": error,
        }


_fundamental_agent: Optional[FundamentalAnalystAgent] = None


def get_fundamental_agent() -> FundamentalAnalystAgent:
    global _fundamental_agent
    if _fundamental_agent is None:
        _fundamental_agent = FundamentalAnalystAgent()
    return _fundamental_agent
