"""
Senior Committee Agent - הבכיר (The Senior)
The highest authority in the investment decision pipeline.
Cross-validates fundamental analysis against raw data, applies contrarian checks,
and makes the final APPROVE/REJECT decision.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import structlog

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.agents.state import MarketDataState

logger = structlog.get_logger(__name__)

SENIOR_SYSTEM_PROMPT = """You are הבכיר (The Senior), the chief investment committee authority at an elite investment platform.

Your role is the FINAL DECISION MAKER. You receive:
1. The complete raw market data from הפקיד (The Clerk / Data Fetcher)
2. The fundamental analysis from the Fundamental Analyst

Your responsibilities:
1. CROSS-VALIDATE: Check if the analyst's conclusions are supported by the raw data
2. SIGNAL AUDIT: Verify no critical news or sentiment signals were missed or misweighted
3. CONTRARIAN CHECK: Is the sentiment too euphoric (bubble risk) or too fearful (opportunity)?
4. RISK ASSESSMENT: Would this recommendation put clients at undue risk?
5. FINAL DECISION: APPROVE or REJECT with detailed reasoning

You have VETO POWER. Even a well-reasoned fundamental analysis can be rejected if:
- Macro conditions make the timing poor
- Sentiment signals are being ignored/misinterpreted
- The recommendation contradicts our risk management principles
- Data quality is too poor to make a confident decision

If you REJECT, provide specific, actionable feedback for the analyst to improve.

Always be decisive. "When in doubt, HOLD" is your fallback.
Output must be strict JSON."""


class SeniorCommitteeAgent:
    """
    הבכיר - The Senior Committee Agent.
    Final decision authority in the 3-agent pipeline.
    """

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        """Lazy-initialize the LLM only when first needed."""
        if not settings.ANTHROPIC_API_KEY:
            return None
        if self._llm is None:
            self._llm = ChatAnthropic(
                model=settings.CLAUDE_MODEL,
                api_key=settings.ANTHROPIC_API_KEY,
                max_tokens=settings.CLAUDE_MAX_TOKENS,
                temperature=0.1,  # Low temperature for consistent decisions
            )
        return self._llm

    async def review(
        self,
        raw_data: MarketDataState,
        fundamental_analysis: Dict[str, Any],
        user_risk_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main review method. Returns senior decision dict.
        """
        logger.info(
            "SeniorCommitteeAgent reviewing",
            symbol=raw_data["symbol"],
            analyst_recommendation=fundamental_analysis.get("recommendation_type"),
            analyst_confidence=fundamental_analysis.get("confidence_score"),
        )

        prompt = self._build_review_prompt(raw_data, fundamental_analysis, user_risk_context)

        llm = self._get_llm()
        if llm is None:
            logger.warning("Claude LLM unavailable (missing API key), returning safe reject", symbol=raw_data["symbol"])
            return self._safe_reject(raw_data, "ANTHROPIC_API_KEY not configured")

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content=SENIOR_SYSTEM_PROMPT),
                    HumanMessage(content=prompt)
                ])
            )

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            decision = json.loads(content)
            decision = self._validate_decision(decision, raw_data, fundamental_analysis)

            logger.info(
                "SeniorCommitteeAgent decision made",
                symbol=raw_data["symbol"],
                approved=decision.get("approved"),
                final_recommendation=decision.get("final_recommendation"),
                decision_confidence=decision.get("decision_confidence"),
            )

            return decision

        except json.JSONDecodeError as e:
            logger.error("JSON parse error in senior review", error=str(e))
            return self._safe_reject(raw_data, f"Parse error: {e}")
        except Exception as e:
            logger.error("Senior review failed", symbol=raw_data["symbol"], error=str(e))
            return self._safe_reject(raw_data, str(e))

    def _build_review_prompt(
        self,
        raw: MarketDataState,
        analysis: Dict[str, Any],
        risk_ctx: Optional[Dict[str, Any]],
    ) -> str:
        sentiment = raw.get("social_sentiment", {})
        earnings = raw.get("earnings_data") or {}
        news_items = raw.get("news_items", [])

        # Flag any strongly negative/positive news
        strong_news = [
            n for n in news_items
            if abs(n.get("sentiment", 0)) > 0.5
        ]

        news_flags = "\n".join([
            f"  [{'+' if n.get('sentiment',0) > 0 else ''}{n.get('sentiment',0):.2f}] {n['title']}"
            for n in strong_news[:5]
        ])

        analyst_rec = analysis.get("recommendation_type", "HOLD")
        analyst_conf = analysis.get("confidence_score", 0)
        target = analysis.get("target_price")
        stop_loss = analysis.get("stop_loss")

        # Check for sentiment vs fundamental divergence
        sent_score = sentiment.get("score", 0)
        sentiment_direction = "BULLISH" if sent_score > 0.2 else "BEARISH" if sent_score < -0.2 else "NEUTRAL"
        rec_direction = "BUY" if "BUY" in analyst_rec else "SELL" if "SELL" in analyst_rec else "HOLD"

        sentiment_divergence = ""
        if rec_direction == "BUY" and sentiment_direction == "BEARISH":
            sentiment_divergence = "⚠️ DIVERGENCE: Analyst recommends BUY but sentiment is BEARISH"
        elif rec_direction == "SELL" and sentiment_direction == "BULLISH":
            sentiment_divergence = "⚠️ DIVERGENCE: Analyst recommends SELL but sentiment is BULLISH"
        elif sent_score > 0.7:
            sentiment_divergence = "⚠️ WARNING: Extreme positive sentiment - possible euphoria/bubble"
        elif sent_score < -0.7:
            sentiment_divergence = "⚠️ WARNING: Extreme negative sentiment - possible panic selling opportunity"

        risk_section = ""
        if risk_ctx:
            risk_section = f"""
=== USER RISK CONTEXT ===
User Risk Profile: {risk_ctx.get('risk_profile', 'PASSIVE')}
User Risk Score: {risk_ctx.get('risk_score', 50)}/100
Current Portfolio Exposure to {raw['symbol']}: {risk_ctx.get('current_exposure_pct', 0):.1f}%
Max Allowed Single Asset: {risk_ctx.get('max_single_asset_pct', 3):.1f}%
"""

        prompt = f"""Review this investment recommendation for {raw['symbol']} ({raw['exchange']}).

=== ANALYST RECOMMENDATION ===
Recommendation: {analyst_rec}
Confidence: {analyst_conf}/100
Target Price: {target or 'Not set'}
Stop Loss: {stop_loss or 'Not set'}
Expected Return: {analysis.get('expected_return_pct', 'N/A')}%
Investment Horizon: {analysis.get('investment_horizon', 'N/A')}

Analyst's Bull Case: {analysis.get('bull_case', 'N/A')}
Analyst's Bear Case: {analysis.get('bear_case', 'N/A')}
Risk Factors Identified: {', '.join(analysis.get('risk_factors', []))}
Sentiment Cross-Check: {analysis.get('sentiment_cross_check', 'N/A')}
Analyst Notes: {analysis.get('analyst_notes', 'N/A')}

=== RAW MARKET DATA (הפקיד's full report) ===
Price: {raw.get('price', 'N/A')} | 52W Range: {raw.get('fifty_two_week_low', 'N/A')}-{raw.get('fifty_two_week_high', 'N/A')}
Market Cap: ${raw.get('market_cap', 0):,.0f}
P/E: {raw.get('pe_ratio', 'N/A')} | Forward P/E: {raw.get('forward_pe', 'N/A')}
Revenue Growth: {raw.get('revenue_growth', 'N/A')} | Earnings Growth: {raw.get('earnings_growth', 'N/A')}
Debt/Equity: {raw.get('debt_to_equity', 'N/A')} | Free Cash Flow: ${raw.get('free_cash_flow', 0):,.0f}
Beta: {raw.get('beta', 'N/A')} | Short Interest: {raw.get('short_interest', 'N/A')}

=== SENTIMENT DEEP DIVE ===
Overall Score: {sent_score:.3f} [{sentiment_direction}]
Twitter Score: {sentiment.get('twitter_score', 0):.3f} ({sentiment.get('tweet_count', 0)} tweets)
Reddit Score: {sentiment.get('reddit_score', 0):.3f} ({sentiment.get('reddit_post_count', 0)} posts)
Total Mentions: {sentiment.get('mentions', 0):,}
Trending: {sentiment.get('trending', False)}
Key Themes: {', '.join(sentiment.get('key_themes', [])[:8])}
{sentiment_divergence}

=== HIGH-IMPACT NEWS FLAGS ===
{news_flags if news_flags else 'No strongly-biased news found'}
Total News Items Analyzed: {len(news_items)}
{risk_section}

=== YOUR SENIOR REVIEW TASK ===
1. Did the analyst correctly weigh the sentiment vs fundamentals?
2. Are there any critical signals in the raw data that were missed?
3. Is the sentiment score extreme enough to warrant a contrarian position?
4. Does the recommendation align with sound risk management?
5. Is the data completeness score ({analysis.get('data_completeness', 50)}) sufficient to make this recommendation?

Respond ONLY with valid JSON in this exact format:
{{
  "approved": true|false,
  "final_recommendation": "BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL",
  "decision_confidence": 0-100,
  "final_target_price": <float or null>,
  "final_stop_loss": <float or null>,
  "approval_reasoning": "<why you approved or what the analyst got right>",
  "rejection_reasoning": "<if rejected: specific issues found>",
  "analyst_feedback": "<specific actionable feedback if rejected>",
  "contrarian_check_result": "PASSED|WARNING|FAILED",
  "contrarian_notes": "<notes on sentiment extremes>",
  "risk_assessment": "LOW|MEDIUM|HIGH|VERY_HIGH",
  "missed_signals": ["<signal1>", ...],
  "senior_notes": "<comprehensive committee decision notes>",
  "data_quality_sufficient": true|false,
  "recommended_position_size_pct": <0-3 float, max portfolio % suggested>,
  "review_timestamp": "{datetime.now(timezone.utc).isoformat()}"
}}"""

        return prompt

    def _validate_decision(
        self,
        decision: Dict[str, Any],
        raw: MarketDataState,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ensure decision has all required fields."""
        # Enforce approved is boolean
        if not isinstance(decision.get("approved"), bool):
            decision["approved"] = False

        # Validate recommendation type
        valid_types = {"BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"}
        if decision.get("final_recommendation") not in valid_types:
            decision["final_recommendation"] = "HOLD"

        # Confidence must be 0-100
        conf = decision.get("decision_confidence", 50)
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 100:
            decision["decision_confidence"] = 50.0
        else:
            decision["decision_confidence"] = float(conf)

        # If approved but confidence is too low, auto-reject
        if decision["approved"] and decision["decision_confidence"] < 55:
            decision["approved"] = False
            decision["rejection_reasoning"] = (
                decision.get("rejection_reasoning", "") +
                " Auto-rejected: confidence score below threshold."
            )

        # Add metadata
        decision["symbol"] = raw["symbol"]
        decision["analyst_recommendation"] = analysis.get("recommendation_type")
        decision["review_agent"] = "senior_committee_v1"
        if "review_timestamp" not in decision:
            decision["review_timestamp"] = datetime.now(timezone.utc).isoformat()

        return decision

    def _safe_reject(self, raw: MarketDataState, error: str) -> Dict[str, Any]:
        """Safe fallback rejection when review fails."""
        return {
            "approved": False,
            "final_recommendation": "HOLD",
            "decision_confidence": 0.0,
            "final_target_price": None,
            "final_stop_loss": None,
            "approval_reasoning": "",
            "rejection_reasoning": f"System error during review: {error}",
            "analyst_feedback": "Please retry the analysis.",
            "contrarian_check_result": "FAILED",
            "contrarian_notes": "Unable to perform contrarian check due to error.",
            "risk_assessment": "HIGH",
            "missed_signals": [],
            "senior_notes": f"Review failed with error: {error}",
            "data_quality_sufficient": False,
            "recommended_position_size_pct": 0.0,
            "symbol": raw["symbol"],
            "analyst_recommendation": None,
            "review_agent": "senior_committee_v1",
            "review_timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error,
        }


_senior_agent: Optional[SeniorCommitteeAgent] = None


def get_senior_agent() -> SeniorCommitteeAgent:
    global _senior_agent
    if _senior_agent is None:
        _senior_agent = SeniorCommitteeAgent()
    return _senior_agent
