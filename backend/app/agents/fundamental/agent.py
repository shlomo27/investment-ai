"""
Fundamental Analyst Agent
Performs deep fundamental analysis on market data collected by הפקיד.
Uses Claude to reason about P/E, earnings quality, sector comparison, etc.
Supports Long/Short hedge fund mode via direction_bias parameter.
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

SYSTEM_PROMPT = """You are a senior fundamental analyst at a Long/Short equity hedge fund.
Your mandate is to generate alpha on BOTH sides of the market — identifying longs and shorts with equal rigor.

For LONG candidates: find undervalued, high-quality companies with improving fundamentals and catalysts.
For SHORT candidates: find overvalued, deteriorating businesses with negative catalysts, weak balance sheets, or structural headwinds.

You analyze stocks with rigorous financial discipline:
1. Evaluate key financial ratios (P/E, PEG, P/B, P/S, debt ratios)
2. Assess earnings quality and revenue growth sustainability
3. Analyze free cash flow generation and burn rate
4. Compare against sector benchmarks and identify relative value
5. Cross-reference financial health with news flow and sentiment
6. For shorts: identify specific catalysts that will cause the stock to decline
7. Provide precise entry levels, targets, and stop-losses

IMPORTANT — When live market data is unavailable (price shown as 0.0 or N/A):
- Use your training knowledge about the company's fundamentals, business model, competitive position
- You MUST still provide a meaningful recommendation — do not default to HOLD with 0 confidence
- Set confidence_score to 30-60 when relying on training knowledge
- A well-reasoned BUY or SELL based on known fundamentals is far more useful than refusing to analyze

Your output must be structured JSON. Be precise and data-driven."""


class FundamentalAnalystAgent:
    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if not settings.ANTHROPIC_API_KEY:
            return None
        if self._llm is None:
            self._llm = ChatAnthropic(
                model=settings.CLAUDE_MODEL,
                api_key=settings.ANTHROPIC_API_KEY,
                max_tokens=settings.CLAUDE_MAX_TOKENS,
                temperature=0.2,
            )
        return self._llm

    async def analyze(
        self,
        market_data: MarketDataState,
        portfolio_context: Optional[Dict[str, Any]] = None,
        news_analysis: Optional[Dict[str, Any]] = None,
        macro_analysis: Optional[Dict[str, Any]] = None,
        direction_bias: Optional[str] = None,
    ) -> Dict[str, Any]:
        logger.info(
            "FundamentalAnalystAgent starting analysis",
            symbol=market_data["symbol"],
            price=market_data.get("price"),
            direction_bias=direction_bias,
        )

        prompt = self._build_analysis_prompt(
            market_data, portfolio_context, news_analysis, macro_analysis, direction_bias
        )

        llm = self._get_llm()
        if llm is None:
            logger.warning("Claude LLM unavailable (missing API key), returning fallback", symbol=market_data["symbol"])
            return self._fallback_analysis(market_data, "ANTHROPIC_API_KEY not configured")

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: llm.invoke([
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
            analysis = self._validate_and_normalize(analysis, market_data, direction_bias)

            logger.info(
                "FundamentalAnalystAgent completed",
                symbol=market_data["symbol"],
                recommendation=analysis.get("recommendation_type"),
                confidence=analysis.get("confidence_score"),
                direction_bias=direction_bias,
            )

            return analysis

        except json.JSONDecodeError as e:
            logger.error("JSON parse error in fundamental analysis", error=str(e))
            return self._fallback_analysis(market_data, f"JSON parse error: {e}")
        except Exception as e:
            logger.error("Fundamental analysis failed", symbol=market_data["symbol"], error=str(e))
            return self._fallback_analysis(market_data, str(e))

    @staticmethod
    def _v(value: Any, default: Any = "N/A") -> Any:
        return value if value is not None else default

    def _build_analysis_prompt(
        self,
        data: MarketDataState,
        portfolio_context: Optional[Dict[str, Any]],
        news_analysis: Optional[Dict[str, Any]] = None,
        macro_analysis: Optional[Dict[str, Any]] = None,
        direction_bias: Optional[str] = None,
    ) -> str:
        v = self._v
        news_summary = "\n".join([
            f"  - [{n.get('sentiment', 0):+.2f}] {n['title']} ({n['source']})"
            for n in data.get("news_items", [])[:8]
        ])

        sentiment = data.get("social_sentiment") or {}
        earnings = data.get("earnings_data") or {}

        # Direction-specific instruction block
        if direction_bias == "SHORT":
            direction_block = """
=== SCREENER DIRECTIVE ===
BIAS: SHORT — The pre-screener flagged this stock as a SHORT CANDIDATE.
Your job: validate or refute the short thesis.
- If you confirm the short: recommend SELL or STRONG_SELL
- Set entry price = current price or slightly above (short entry level)
- Set target_price = your downside target (where you'd cover the short)
- Set stop_loss = where you'd cut the loss (above current price for a short)
- expected_return_pct should be NEGATIVE (the expected decline)
Focus on: overvaluation, deteriorating margins, competitive threats, debt stress, insider selling, high short interest as confirmation, upcoming negative catalysts.
"""
        elif direction_bias == "LONG":
            direction_block = """
=== SCREENER DIRECTIVE ===
BIAS: LONG — The pre-screener flagged this stock as a LONG CANDIDATE.
Your job: validate or refute the long thesis.
- If you confirm the long: recommend BUY or STRONG_BUY
- Set target_price = your upside target
- Set stop_loss = where you'd cut the loss (below current price)
- expected_return_pct should be POSITIVE
Focus on: undervaluation, improving fundamentals, strong FCF, margin expansion, upcoming positive catalysts, analyst upgrades.
"""
        else:
            direction_block = """
=== ANALYSIS MODE ===
BIAS: NEUTRAL — Evaluate this stock objectively for both long and short potential.
Recommend BUY if it's a compelling long, SELL if it's a compelling short, HOLD if neither is clear.
"""

        portfolio_section = ""
        if portfolio_context:
            portfolio_section = f"""
=== PORTFOLIO CONTEXT ===
Total Portfolio Value: ${v(portfolio_context.get('total_value'), 0):,.2f}
Available Cash: ${v(portfolio_context.get('cash_balance'), 0):,.2f}
Current Holdings: {portfolio_context.get('holdings_count', 0)} positions
Max Single Asset Exposure: {portfolio_context.get('max_exposure_pct', 3)}%
Existing Position in {data['symbol']}: {portfolio_context.get('existing_position', 'None')}
"""

        prompt = f"""Perform comprehensive fundamental analysis for {data['symbol']} ({data['exchange']}).
{direction_block}
=== MARKET DATA ===
Current Price: {v(data.get('price'), 'N/A')} {v(data.get('currency'), 'USD')}
Previous Close: {v(data.get('previous_close'), 'N/A')}
52-Week Range: {v(data.get('fifty_two_week_low'), 'N/A')} – {v(data.get('fifty_two_week_high'), 'N/A')}
Volume: {v(data.get('volume'), 0):,} (30d avg: {v(data.get('avg_volume_30d'), 0):,})
Market Cap: ${v(data.get('market_cap'), 0):,.0f}
Sector: {v(data.get('sector'), 'Unknown')} | Industry: {v(data.get('industry'), 'Unknown')}
Country: {v(data.get('country'), 'US')}

=== VALUATION RATIOS ===
P/E Ratio (TTM): {v(data.get('pe_ratio'), 'N/A')}
Forward P/E: {v(data.get('forward_pe'), 'N/A')}
PEG Ratio: {v(data.get('peg_ratio'), 'N/A')}
Price/Book: {v(data.get('price_to_book'), 'N/A')}
Price/Sales: {v(data.get('price_to_sales'), 'N/A')}
Analyst Target: {v(data.get('analyst_target_price'), 'N/A')} | Analyst Rec: {v(data.get('analyst_recommendation'), 'N/A')}

=== FINANCIAL HEALTH ===
Revenue Growth (YoY): {v(data.get('revenue_growth'), 'N/A')}
Earnings Growth (YoY): {v(data.get('earnings_growth'), 'N/A')}
Profit Margin: {v(data.get('profit_margin'), 'N/A')}
Operating Margin: {v(data.get('operating_margin'), 'N/A')}
ROE: {v(data.get('roe'), 'N/A')}
ROA: {v(data.get('roa'), 'N/A')}
Free Cash Flow: ${v(data.get('free_cash_flow'), 0):,.0f}
Debt/Equity: {v(data.get('debt_to_equity'), 'N/A')}
Current Ratio: {v(data.get('current_ratio'), 'N/A')}
Quick Ratio: {v(data.get('quick_ratio'), 'N/A')}
Beta: {v(data.get('beta'), 'N/A')}
Dividend Yield: {v(data.get('dividend_yield'), 'N/A')}
Institutional Ownership: {v(data.get('institutional_ownership'), 'N/A')}
Short Interest: {v(data.get('short_interest'), 'N/A')}

=== EARNINGS ===
Last EPS: {v(earnings.get('last_eps'), 'N/A')} (Estimate: {v(earnings.get('eps_estimate'), 'N/A')}, Surprise: {v(earnings.get('eps_surprise_pct'), 'N/A')}%)
Revenue Last: ${v(earnings.get('revenue_last'), 0):,.0f} (Estimate: ${v(earnings.get('revenue_estimate'), 0):,.0f})
Next Earnings Date: {v(earnings.get('earnings_date'), 'N/A')}

=== SOCIAL SENTIMENT ===
Overall Sentiment Score: {sentiment.get('score', 0):.3f} (-1 bearish to +1 bullish)
Total Mentions: {sentiment.get('mentions', 0):,}
Twitter Score: {sentiment.get('twitter_score', 0):.3f} ({sentiment.get('tweet_count', 0)} tweets)
Reddit Score: {sentiment.get('reddit_score', 0):.3f} ({sentiment.get('reddit_post_count', 0)} posts)
Trending: {sentiment.get('trending', False)}
Key Themes: {', '.join(sentiment.get('key_themes', [])[:5])}

=== RECENT NEWS ===
{news_summary if news_summary else 'No recent news available'}

=== GPT NEWS ANALYSIS ===
{self._format_news_analysis(news_analysis)}

=== GEMINI MACRO CONTEXT ===
{self._format_macro_analysis(macro_analysis)}
{portfolio_section}
=== COMPANY CONTEXT ===
{data.get('company_description', 'No description available.')}

---

Based on ALL the above data and the screener directive, provide your analysis in this exact JSON format:
{{
  "recommendation_type": "BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL",
  "direction_bias": "{direction_bias or 'NEUTRAL'}",
  "confidence_score": 0-100,
  "target_price": <float or null — for SHORT: downside target; for LONG: upside target>,
  "stop_loss": <float or null — for SHORT: above entry; for LONG: below entry>,
  "expected_return_pct": <float — NEGATIVE for short thesis, POSITIVE for long thesis>,
  "investment_horizon": "SHORT_TERM|MEDIUM_TERM|LONG_TERM",
  "valuation_assessment": "UNDERVALUED|FAIRLY_VALUED|OVERVALUED",
  "financial_health": "EXCELLENT|GOOD|FAIR|POOR",
  "thesis": "<2-3 sentences describing the core long or short thesis>",
  "key_metrics_summary": {{
    "pe_assessment": "<text>",
    "growth_quality": "<text>",
    "balance_sheet_strength": "<text>",
    "cash_flow_quality": "<text>",
    "sentiment_alignment": "<text>"
  }},
  "bull_case": "<2-3 sentences>",
  "bear_case": "<2-3 sentences>",
  "short_catalysts": ["<catalyst1>", "<catalyst2>"],
  "risk_factors": ["<risk1>", "<risk2>"],
  "catalysts": ["<catalyst1>", "<catalyst2>"],
  "sector_comparison": "<text>",
  "sentiment_cross_check": "<text>",
  "analyst_notes": "<detailed analysis notes>",
  "data_completeness": 0-100
}}"""

        return prompt

    @staticmethod
    def _format_news_analysis(news: Optional[Dict[str, Any]]) -> str:
        if not news or news.get("skipped_reason"):
            return "Not available"
        return (
            f"Dominant Narrative: {news.get('dominant_narrative', 'N/A')}\n"
            f"Overall Impact: {news.get('overall_market_impact', 'N/A')} / Direction: {news.get('overall_direction', 'N/A')}\n"
            f"Sentiment-News Alignment: {news.get('sentiment_news_alignment', 'N/A')}\n"
            f"Hidden Signals: {', '.join(news.get('hidden_signals') or [])}\n"
            f"Red Flags: {', '.join(news.get('red_flags') or [])}\n"
            f"Opportunities: {', '.join(news.get('opportunities') or [])}"
        )

    @staticmethod
    def _format_macro_analysis(macro: Optional[Dict[str, Any]]) -> str:
        if not macro or macro.get("skipped_reason"):
            return "Not available"
        return (
            f"Sector Outlook: {macro.get('sector_outlook', 'N/A')} | {macro.get('sector_trend', 'N/A')}\n"
            f"Macro Environment: {macro.get('macro_environment', 'N/A')}\n"
            f"Macro Impact on Stock: {macro.get('macro_impact_on_stock', 'N/A')}\n"
            f"Competitive Position: {macro.get('competitive_position', 'N/A')} — {macro.get('competitive_notes', 'N/A')}\n"
            f"Regulatory Risk: {macro.get('regulatory_risk', 'N/A')} — {macro.get('regulatory_notes', 'N/A')}\n"
            f"Analyst Consensus Trend: {macro.get('analyst_consensus_trend', 'N/A')}\n"
            f"Key Macro Risks: {', '.join(macro.get('key_macro_risks') or [])}\n"
            f"Key Macro Catalysts: {', '.join(macro.get('key_macro_catalysts') or [])}"
        )

    def _validate_and_normalize(
        self,
        analysis: Dict[str, Any],
        data: MarketDataState,
        direction_bias: Optional[str] = None,
    ) -> Dict[str, Any]:
        valid_rec_types = {"BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"}

        if analysis.get("recommendation_type") not in valid_rec_types:
            analysis["recommendation_type"] = "HOLD"

        # Enforce directional consistency
        rec = analysis.get("recommendation_type", "HOLD")
        if direction_bias == "SHORT" and rec in ("BUY", "STRONG_BUY"):
            # Analyst contradicts short bias — downgrade to HOLD as a safety measure
            analysis["recommendation_type"] = "HOLD"
            analysis["direction_override_note"] = "Bias was SHORT but analyst recommended BUY — downgraded to HOLD for senior review"
        elif direction_bias == "LONG" and rec in ("SELL", "STRONG_SELL"):
            analysis["recommendation_type"] = "HOLD"
            analysis["direction_override_note"] = "Bias was LONG but analyst recommended SELL — downgraded to HOLD for senior review"

        confidence = analysis.get("confidence_score", 50)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 100:
            analysis["confidence_score"] = 50.0
        else:
            analysis["confidence_score"] = float(confidence)

        analysis["symbol"] = data["symbol"]
        analysis["direction_bias"] = direction_bias or "NEUTRAL"
        analysis["analysis_timestamp"] = datetime.now(timezone.utc).isoformat()
        analysis["analyst_id"] = "fundamental_agent_v1"

        return analysis

    def _fallback_analysis(self, data: MarketDataState, error: str) -> Dict[str, Any]:
        return {
            "recommendation_type": "HOLD",
            "direction_bias": "NEUTRAL",
            "confidence_score": 0.0,
            "target_price": None,
            "stop_loss": None,
            "expected_return_pct": None,
            "investment_horizon": "MEDIUM_TERM",
            "valuation_assessment": "FAIRLY_VALUED",
            "financial_health": "FAIR",
            "thesis": "Analysis unavailable due to system error.",
            "key_metrics_summary": {},
            "bull_case": "Analysis unavailable due to system error.",
            "bear_case": "Analysis unavailable due to system error.",
            "short_catalysts": [],
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
