"""
Senior Committee Agent - הבכיר (The Senior)
The highest authority in the investment decision pipeline.
Cross-validates fundamental analysis against raw data, applies contrarian checks,
and makes the final APPROVE/REJECT decision.
Supports Long/Short hedge fund strategy via direction_bias parameter.
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

SENIOR_SYSTEM_PROMPT = """You are הבכיר (The Senior), the chief investment committee authority at a Long/Short equity hedge fund.

Your role is the FINAL DECISION MAKER. You receive:
1. The complete raw market data from הפקיד (The Clerk / Data Fetcher)
2. The fundamental analysis from the Fundamental Analyst
3. The pre-screener direction bias (LONG, SHORT, or NEUTRAL)

Your responsibilities:
1. CROSS-VALIDATE: Check if the analyst's conclusions are supported by the raw data
2. DIRECTIONAL CHECK: For LONG — confirm the stock is genuinely undervalued with a catalyst. For SHORT — confirm the deterioration thesis is solid and there's a specific downside catalyst.
3. SIGNAL AUDIT: Verify no critical news or sentiment signals were missed
4. CONTRARIAN CHECK: Is the sentiment too euphoric (bubble/short squeeze risk) or too fearful (opportunity)?
5. RISK ASSESSMENT: Size the position appropriately. Shorts carry unlimited theoretical loss risk.
6. FINAL DECISION: APPROVE or REJECT with detailed reasoning

For SHORT recommendations: you are especially rigorous. Verify:
- Clear overvaluation vs peers
- A specific catalyst for decline (earnings miss, margin compression, competition, etc.)
- Stop-loss is defined and reasonable
- Short interest isn't already extreme (squeeze risk)

You have VETO POWER. "When in doubt, HOLD" is your fallback.
Output must be strict JSON."""


class SeniorCommitteeAgent:
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
                temperature=0.1,
            )
        return self._llm

    @staticmethod
    def _language_instruction(language: str) -> str:
        if language == "he":
            return (
                "\n\nLANGUAGE: Write ALL free-text fields in Hebrew (עברית). "
                "This includes: approval_reasoning, rejection_reasoning, senior_notes, "
                "contrarian_check_result, risk_assessment_notes. "
                "Keep stock symbols, numeric values, percentages, and enum values "
                "(BUY, STRONG_BUY, HOLD, SELL, STRONG_SELL, APPROVE, REJECT) in English."
            )
        return ""

    async def review(
        self,
        raw_data: MarketDataState,
        fundamental_analysis: Dict[str, Any],
        news_analysis: Optional[Dict[str, Any]] = None,
        macro_analysis: Optional[Dict[str, Any]] = None,
        user_risk_context: Optional[Dict[str, Any]] = None,
        direction_bias: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        logger.info(
            "SeniorCommitteeAgent reviewing",
            symbol=raw_data["symbol"],
            analyst_recommendation=fundamental_analysis.get("recommendation_type"),
            analyst_confidence=fundamental_analysis.get("confidence_score"),
            direction_bias=direction_bias,
        )

        prompt = self._build_review_prompt(raw_data, fundamental_analysis, user_risk_context, direction_bias, news_analysis, macro_analysis)

        llm = self._get_llm()
        if llm is None:
            logger.warning("Claude LLM unavailable (missing API key), returning safe reject", symbol=raw_data["symbol"])
            return self._safe_reject(raw_data, "ANTHROPIC_API_KEY not configured")

        system_content = SENIOR_SYSTEM_PROMPT + self._language_instruction(language)

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: llm.invoke([
                    SystemMessage(content=system_content),
                    HumanMessage(content=prompt)
                ])
            )

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            decision = json.loads(content)
            decision = self._validate_decision(decision, raw_data, fundamental_analysis, direction_bias)

            logger.info(
                "SeniorCommitteeAgent decision made",
                symbol=raw_data["symbol"],
                approved=decision.get("approved"),
                final_recommendation=decision.get("final_recommendation"),
                decision_confidence=decision.get("decision_confidence"),
                direction_bias=direction_bias,
            )

            return decision

        except json.JSONDecodeError as e:
            logger.error("JSON parse error in senior review", error=str(e))
            return self._safe_reject(raw_data, f"Parse error: {e}")
        except Exception as e:
            logger.error("Senior review failed", symbol=raw_data["symbol"], error=str(e))
            return self._safe_reject(raw_data, str(e))

    @staticmethod
    def _v(value: Any, default: Any = "N/A") -> Any:
        return value if value is not None else default

    def _build_review_prompt(
        self,
        raw: MarketDataState,
        analysis: Dict[str, Any],
        risk_ctx: Optional[Dict[str, Any]],
        direction_bias: Optional[str] = None,
        news_analysis: Optional[Dict[str, Any]] = None,
        macro_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        sentiment = raw.get("social_sentiment") or {}
        earnings = raw.get("earnings_data") or {}
        news_items = raw.get("news_items", [])

        strong_news = [n for n in news_items if abs(n.get("sentiment", 0)) > 0.5]
        news_flags = "\n".join([
            f"  [{'+' if n.get('sentiment',0) > 0 else ''}{n.get('sentiment',0):.2f}] {n['title']}"
            for n in strong_news[:5]
        ])

        analyst_rec = analysis.get("recommendation_type", "HOLD")
        analyst_conf = analysis.get("confidence_score", 0)
        target = analysis.get("target_price")
        stop_loss = analysis.get("stop_loss")

        sent_score = sentiment.get("score", 0)
        sentiment_direction = "BULLISH" if sent_score > 0.2 else "BEARISH" if sent_score < -0.2 else "NEUTRAL"
        rec_direction = "BUY" if "BUY" in analyst_rec else "SELL" if "SELL" in analyst_rec else "HOLD"

        sentiment_divergence = ""
        if rec_direction == "BUY" and sentiment_direction == "BEARISH":
            sentiment_divergence = "⚠️ DIVERGENCE: Analyst recommends BUY but sentiment is BEARISH"
        elif rec_direction == "SELL" and sentiment_direction == "BULLISH":
            sentiment_divergence = "⚠️ DIVERGENCE: Analyst recommends SELL but sentiment is BULLISH (short squeeze risk!)"
        elif sent_score > 0.7:
            sentiment_divergence = "⚠️ WARNING: Extreme positive sentiment — possible euphoria/bubble"
        elif sent_score < -0.7:
            sentiment_divergence = "⚠️ WARNING: Extreme negative sentiment — possible panic opportunity"

        # Direction-specific review checklist
        if direction_bias == "SHORT":
            direction_checklist = """
=== SHORT POSITION REVIEW CHECKLIST ===
Verify ALL of the following before approving a SHORT:
□ Clear overvaluation relative to sector peers (P/E, EV/EBITDA, P/S)
□ Specific negative catalyst identified (earnings miss, margin compression, competition, regulatory, etc.)
□ Stop-loss is defined and set above entry (not too tight — short squeezes happen)
□ Short interest < 20% of float (avoid crowded shorts unless squeeze risk is addressed)
□ No imminent positive catalyst that could cause a squeeze (earnings surprise, acquisition rumor, etc.)
□ Institutional ownership is declining or the stock is being downgraded
"""
        elif direction_bias == "LONG":
            direction_checklist = """
=== LONG POSITION REVIEW CHECKLIST ===
Verify ALL of the following before approving a LONG:
□ Stock is undervalued vs sector peers on at least 2 valuation metrics
□ Specific positive catalyst identified (earnings acceleration, margin expansion, new product, etc.)
□ Stop-loss is defined and set below entry with acceptable risk/reward (min 2:1)
□ Company has adequate financial health (not on the verge of bankruptcy for deep-value plays)
□ Sentiment is not euphoric (avoid crowded longs at peak sentiment)
"""
        else:
            direction_checklist = """
=== NEUTRAL REVIEW ===
Evaluate the recommendation on its own merits. Require clear evidence for any non-HOLD recommendation.
"""

        risk_section = ""
        if risk_ctx:
            risk_section = f"""
=== FUND RISK CONTEXT ===
Fund Risk Profile: {risk_ctx.get('risk_profile', 'MODERATE')}
Current Exposure to {raw['symbol']}: {risk_ctx.get('current_exposure_pct', 0):.1f}%
Max Allowed Single Position: {risk_ctx.get('max_single_asset_pct', 3):.1f}%
"""

        # Format GPT news analysis for senior
        news_section = ""
        if news_analysis and not news_analysis.get("skipped_reason"):
            news_section = f"""
=== GPT NEWS INTELLIGENCE (Direct from News Analyst) ===
Dominant Narrative: {news_analysis.get('dominant_narrative', 'N/A')}
Overall Impact: {news_analysis.get('overall_market_impact', 'N/A')} / Direction: {news_analysis.get('overall_direction', 'N/A')}
Sentiment-News Alignment: {news_analysis.get('sentiment_news_alignment', 'N/A')}
Hidden Signals: {', '.join(news_analysis.get('hidden_signals') or []) or 'None'}
Red Flags: {', '.join(news_analysis.get('red_flags') or []) or 'None'}
Opportunities: {', '.join(news_analysis.get('opportunities') or []) or 'None'}
News Quality Score: {news_analysis.get('news_quality_score', 0)}/100
"""

        # Format Gemini macro analysis for senior
        macro_section = ""
        if macro_analysis and not macro_analysis.get("skipped_reason"):
            macro_section = f"""
=== GEMINI MACRO INTELLIGENCE (Direct from Macro Analyst) ===
Sector Outlook: {macro_analysis.get('sector_outlook', 'N/A')} — {macro_analysis.get('sector_trend', 'N/A')}
Macro Environment: {macro_analysis.get('macro_environment', 'N/A')}
Macro Impact on Stock: {macro_analysis.get('macro_impact_on_stock', 'N/A')}
Competitive Position: {macro_analysis.get('competitive_position', 'N/A')} — {macro_analysis.get('competitive_notes', 'N/A')}
Regulatory Risk: {macro_analysis.get('regulatory_risk', 'N/A')} — {macro_analysis.get('regulatory_notes', 'N/A')}
Analyst Consensus Trend: {macro_analysis.get('analyst_consensus_trend', 'N/A')}
Key Macro Risks: {', '.join(macro_analysis.get('key_macro_risks') or []) or 'None'}
Key Macro Catalysts: {', '.join(macro_analysis.get('key_macro_catalysts') or []) or 'None'}
Real-Time Macro: {macro_analysis.get('real_time_macro_summary', 'Not available')}
"""

        v = self._v
        prompt = f"""Review this investment recommendation for {raw['symbol']} ({raw['exchange']}).
Screener Direction Bias: {direction_bias or 'NEUTRAL'}
{direction_checklist}
=== ANALYST RECOMMENDATION ===
Recommendation: {analyst_rec}
Confidence: {analyst_conf}/100
Target Price: {target or 'Not set'}
Stop Loss: {stop_loss or 'Not set'}
Expected Return: {v(analysis.get('expected_return_pct'), 'N/A')}%
Investment Horizon: {v(analysis.get('investment_horizon'), 'N/A')}
Thesis: {v(analysis.get('thesis'), 'N/A')}

Bull Case: {v(analysis.get('bull_case'), 'N/A')}
Bear Case: {v(analysis.get('bear_case'), 'N/A')}
Short Catalysts: {', '.join(analysis.get('short_catalysts') or [])}
Risk Factors: {', '.join(analysis.get('risk_factors') or [])}
Sentiment Cross-Check: {v(analysis.get('sentiment_cross_check'), 'N/A')}
Analyst Notes: {v(analysis.get('analyst_notes'), 'N/A')}
Direction Override Note: {v(analysis.get('direction_override_note'), 'None')}

=== RAW MARKET DATA ===
Price: {v(raw.get('price'), 'N/A')} | 52W Range: {v(raw.get('fifty_two_week_low'), 'N/A')}–{v(raw.get('fifty_two_week_high'), 'N/A')}
Market Cap: ${v(raw.get('market_cap'), 0):,.0f}
P/E: {v(raw.get('pe_ratio'), 'N/A')} | Forward P/E: {v(raw.get('forward_pe'), 'N/A')}
Revenue Growth: {v(raw.get('revenue_growth'), 'N/A')} | Earnings Growth: {v(raw.get('earnings_growth'), 'N/A')}
Debt/Equity: {v(raw.get('debt_to_equity'), 'N/A')} | Free Cash Flow: ${v(raw.get('free_cash_flow'), 0):,.0f}
Beta: {v(raw.get('beta'), 'N/A')} | Short Interest: {v(raw.get('short_interest'), 'N/A')}
Institutional Ownership: {v(raw.get('institutional_ownership'), 'N/A')}

=== SENTIMENT ===
Overall Score: {sent_score:.3f} [{sentiment_direction}]
Twitter Score: {v(sentiment.get('twitter_score'), 0):.3f} ({v(sentiment.get('tweet_count'), 0)} tweets)
Reddit Score: {v(sentiment.get('reddit_score'), 0):.3f} ({v(sentiment.get('reddit_post_count'), 0)} posts)
Total Mentions: {v(sentiment.get('mentions'), 0):,}
{sentiment_divergence}

=== HIGH-IMPACT NEWS (Raw) ===
{news_flags if news_flags else 'No strongly-biased news found'}
Total News Analyzed: {len(news_items)}
{news_section}{macro_section}{risk_section}

Respond ONLY with valid JSON:
{{
  "approved": true|false,
  "final_recommendation": "BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL",
  "direction_bias": "{direction_bias or 'NEUTRAL'}",
  "decision_confidence": 0-100,
  "final_target_price": <float or null>,
  "final_stop_loss": <float or null>,
  "expected_return_pct": <float — negative for shorts>,
  "approval_reasoning": "<why you approved>",
  "rejection_reasoning": "<if rejected: specific issues>",
  "analyst_feedback": "<actionable feedback if rejected>",
  "contrarian_check_result": "PASSED|WARNING|FAILED",
  "contrarian_notes": "<notes on sentiment extremes or squeeze risk>",
  "risk_assessment": "LOW|MEDIUM|HIGH|VERY_HIGH",
  "missed_signals": ["<signal1>"],
  "short_squeeze_risk": "LOW|MEDIUM|HIGH",
  "senior_notes": "<comprehensive decision notes>",
  "data_quality_sufficient": true|false,
  "recommended_position_size_pct": <0-5 float>,
  "review_timestamp": "{datetime.now(timezone.utc).isoformat()}"
}}"""

        return prompt

    def _validate_decision(
        self,
        decision: Dict[str, Any],
        raw: MarketDataState,
        analysis: Dict[str, Any],
        direction_bias: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(decision.get("approved"), bool):
            decision["approved"] = False

        valid_types = {"BUY", "SELL", "HOLD", "STRONG_BUY", "STRONG_SELL"}
        if decision.get("final_recommendation") not in valid_types:
            decision["final_recommendation"] = "HOLD"

        conf = decision.get("decision_confidence", 50)
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 100:
            decision["decision_confidence"] = 50.0
        else:
            decision["decision_confidence"] = float(conf)

        # Auto-reject if approved with too-low confidence
        if decision["approved"] and decision["decision_confidence"] < 30:
            decision["approved"] = False
            decision["rejection_reasoning"] = (
                (decision.get("rejection_reasoning") or "") +
                " Auto-rejected: confidence score below threshold."
            )

        # For SHORT direction: final recommendation must be SELL or STRONG_SELL
        if direction_bias == "SHORT" and decision.get("approved"):
            if decision["final_recommendation"] in ("BUY", "STRONG_BUY"):
                decision["approved"] = False
                decision["rejection_reasoning"] = (
                    "Senior override: SHORT bias but recommendation is BUY — rejecting for safety."
                )

        # For LONG direction: final recommendation must be BUY or STRONG_BUY
        if direction_bias == "LONG" and decision.get("approved"):
            if decision["final_recommendation"] in ("SELL", "STRONG_SELL"):
                decision["approved"] = False
                decision["rejection_reasoning"] = (
                    "Senior override: LONG bias but recommendation is SELL — rejecting for safety."
                )

        decision["symbol"] = raw["symbol"]
        decision["analyst_recommendation"] = analysis.get("recommendation_type")
        decision["direction_bias"] = direction_bias or "NEUTRAL"
        decision["review_agent"] = "senior_committee_v1"
        if "review_timestamp" not in decision:
            decision["review_timestamp"] = datetime.now(timezone.utc).isoformat()

        return decision

    def _safe_reject(self, raw: MarketDataState, error: str) -> Dict[str, Any]:
        return {
            "approved": False,
            "final_recommendation": "HOLD",
            "direction_bias": "NEUTRAL",
            "decision_confidence": 0.0,
            "final_target_price": None,
            "final_stop_loss": None,
            "expected_return_pct": None,
            "approval_reasoning": "",
            "rejection_reasoning": f"System error during review: {error}",
            "analyst_feedback": "Please retry the analysis.",
            "contrarian_check_result": "FAILED",
            "contrarian_notes": "Unable to perform check due to error.",
            "risk_assessment": "HIGH",
            "missed_signals": [],
            "short_squeeze_risk": "MEDIUM",
            "senior_notes": f"Review failed with error: {error}",
            "data_quality_sufficient": False,
            "recommended_position_size_pct": 0.0,
            "symbol": raw["symbol"],
            "analyst_recommendation": None,
            "direction_bias": "NEUTRAL",
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
