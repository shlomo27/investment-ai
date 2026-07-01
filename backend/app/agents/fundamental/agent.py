"""
Fundamental Analyst Agent
Performs deep fundamental analysis on market data collected by הפקיד.
Uses Claude to reason about P/E, earnings quality, sector comparison, etc.
Supports Long/Short hedge fund mode via direction_bias parameter.
"""
import asyncio
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
import numpy as np

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.agents.state import MarketDataState

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a senior fundamental analyst at a $10B institutional long/short equity fund.
Your mandate is to generate alpha on BOTH sides of the market — identifying longs and shorts with equal rigor.

CORE ANALYTICAL FRAMEWORK:
1. Evaluate key financial ratios (P/E, PEG, P/B, P/S, FCF yield, debt ratios)
2. Assess earnings quality and revenue growth sustainability
3. Analyze free cash flow generation relative to dividends, capex, and debt service
4. Compare against sector benchmarks and identify relative value
5. Cross-reference financial health with news flow, sentiment, and macro context
6. Classify competitive moat (one of four specific types defined below)
7. Validate every catalyst against the 5-criterion protocol below
8. Build explicit Bull/Base/Bear scenarios with probability-weighted Expected Value

══════════════════════════════════════════════
HARD EXCLUSION RULES — ZERO TOLERANCE
If ANY rule is confirmed → set auto_disqualified=true, recommendation=HOLD, list in hard_exclusions_triggered
══════════════════════════════════════════════
✗ Revenue declining 3+ consecutive quarters YoY → ELIMINATION
✗ Dividend payout exceeds trailing Free Cash Flow → ELIMINATION (yield trap)
✗ Majority analyst consensus is SELL / STRONG_SELL / UNDERPERFORM → ELIMINATION
✗ Material investigation, litigation, or accounting restatement in past 24 months → ELIMINATION
✗ Confirmed insider selling >20% of holdings in past 6 months (without estate/diversification explanation) → ELIMINATION
✗ Net Debt/EBITDA above 4.5x (exception: regulated utilities/telecoms with contracted revenues ≤5x) → ELIMINATION
✗ Market cap below $500M USD → ELIMINATION
✗ Negative 3-year average FCF → ELIMINATION
If UNCERTAIN whether a rule applies: flag it in hard_exclusions_triggered as "UNCERTAIN: [reason]" — do NOT auto-eliminate based on uncertainty alone.

══════════════════════════════════════════════
CATALYST VALIDATION PROTOCOL — Score 0-5 points
A catalyst earns 1 point for each criterion met:
══════════════════════════════════════════════
1. SPECIFIC: A named, discrete event (not vague "management improving")
2. DATED: Expected within 18 months from today
3. QUANTIFIABLE: States expected % impact on EPS, FCF, or valuation multiple
4. VERIFIABLE: Confirmable via SEC/regulatory filings or company press releases
5. NOT_PRICED_IN: Forward P/E vs historical range shows market hasn't discounted it yet

══════════════════════════════════════════════
MOAT CLASSIFICATION — Choose exactly ONE:
══════════════════════════════════════════════
• COST_MONOPOLY: Structurally lowest-cost producer (not temporary pricing advantage)
• SWITCHING_COST: Verified customer lock-in with quantified cost to switch
• NETWORK_EFFECT: Value grows with user base — quantify marginal value per additional user
• REGULATORY: Licensed or regulated barrier with specific dated legal protection
• NONE: No durable competitive advantage identified
Note: Brand recognition alone is NOT a valid moat for this framework.

══════════════════════════════════════════════
SCENARIO ANALYSIS — Required for every recommendation
Bull + Base + Bear probabilities MUST sum to exactly 100.
══════════════════════════════════════════════
For each scenario: state the specific trigger, a price target, timeline in months, and probability %.
Bull: optimistic but plausible — not a fantasy. Bear: a specific downside risk materializing — not maximum catastrophe.

POSTURE: Every number must be derived from data or explicitly estimated from training knowledge.
State "I don't know" when data is truly unavailable. Never use words: compelling, attractive, exciting, promising.
The burden of proof is on the BUY case, not the AVOID case.
Challenge your own thesis: for each position, state the single strongest argument AGAINST buying.

Your output must be structured JSON. Be precise, data-driven, and intellectually honest."""


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

    @staticmethod
    def _language_instruction(language: str) -> str:
        if language == "he":
            return (
                "\n\nLANGUAGE: Write ALL free-text fields in Hebrew (עברית). "
                "This includes: thesis, bull_case, bear_case, risk_factors, catalysts, "
                "key_metrics_summary, valuation_assessment, financial_health, analyst_notes. "
                "Keep stock symbols, numeric values, percentages, and enum values "
                "(BUY, STRONG_BUY, HOLD, SELL, STRONG_SELL) in English."
            )
        return ""

    async def analyze(
        self,
        market_data: MarketDataState,
        portfolio_context: Optional[Dict[str, Any]] = None,
        news_analysis: Optional[Dict[str, Any]] = None,
        macro_analysis: Optional[Dict[str, Any]] = None,
        direction_bias: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        logger.info(
            "FundamentalAnalystAgent starting analysis",
            symbol=market_data["symbol"],
            price=market_data.get("price"),
            direction_bias=direction_bias,
        )

        quant_models = self._compute_financial_models(market_data)
        logger.info("Quantitative models computed", symbol=market_data["symbol"], models=list(quant_models.keys()))

        pre_exclusions = self._check_hard_exclusions_python(market_data)
        if pre_exclusions:
            logger.info("Python pre-screening flags found", symbol=market_data["symbol"], flags=pre_exclusions)

        prompt = self._build_analysis_prompt(
            market_data, portfolio_context, news_analysis, macro_analysis, direction_bias,
            quant_models=quant_models,
            pre_exclusions=pre_exclusions,
        )

        llm = self._get_llm()
        if llm is None:
            logger.warning("Claude LLM unavailable (missing API key), returning fallback", symbol=market_data["symbol"])
            return self._fallback_analysis(market_data, "ANTHROPIC_API_KEY not configured", quant_models)

        system_content = SYSTEM_PROMPT + self._language_instruction(language)

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

            analysis = json.loads(content)
            analysis = self._validate_and_normalize(analysis, market_data, direction_bias)
            analysis["quantitative_models"] = quant_models

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
            return self._fallback_analysis(market_data, f"JSON parse error: {e}", quant_models)
        except Exception as e:
            logger.error("Fundamental analysis failed", symbol=market_data["symbol"], error=str(e))
            return self._fallback_analysis(market_data, str(e), quant_models)

    @staticmethod
    def _v(value: Any, default: Any = "N/A") -> Any:
        return value if value is not None else default

    @staticmethod
    def _check_hard_exclusions_python(data: MarketDataState) -> List[str]:
        """Python-detectable hard exclusion pre-screening."""
        flags: List[str] = []
        market_cap = float(data.get("market_cap") or 0)
        fcf = float(data.get("free_cash_flow") or 0)
        div_yield = float(data.get("dividend_yield") or 0)
        debt_to_equity = data.get("debt_to_equity")
        analyst_rec = (data.get("analyst_recommendation") or "").lower()
        price = float(data.get("price") or 0)

        if 0 < market_cap < 500_000_000:
            flags.append(f"MICRO-CAP: Market cap ${market_cap/1e6:.0f}M is below $500M minimum threshold")

        if fcf < 0:
            flags.append(f"NEGATIVE FCF: Trailing FCF ${fcf/1e6:.0f}M — verify 3-year average")

        if fcf > 0 and market_cap > 0 and div_yield > 0 and price > 0:
            annual_divs = market_cap * div_yield
            if annual_divs > fcf:
                flags.append(
                    f"DIVIDEND YIELD TRAP: Estimated annual dividends ${annual_divs/1e6:.0f}M "
                    f"exceeds FCF ${fcf/1e6:.0f}M"
                )

        if analyst_rec in ("sell", "strong sell", "underperform", "reduce", "strong_sell"):
            flags.append(f"ANALYST SELL CONSENSUS: Consensus recommendation is '{analyst_rec}'")

        if debt_to_equity is not None and float(debt_to_equity) > 5.0:
            flags.append(
                f"HIGH LEVERAGE: Debt/Equity {float(debt_to_equity):.1f}x — verify Net Debt/EBITDA vs 4.5x limit"
            )

        return flags

    @staticmethod
    def _compute_ev_and_allocation(
        analysis: Dict[str, Any],
        price: float,
    ) -> Dict[str, Any]:
        """Compute Expected Value and allocation recommendation from scenario analysis."""
        scenario = analysis.get("scenario_analysis") or {}
        bull = scenario.get("bull") or {}
        base = scenario.get("base") or {}
        bear = scenario.get("bear") or {}

        if price > 0 and bull.get("price_target") and base.get("price_target") and bear.get("price_target"):
            try:
                bull_p = float(bull.get("probability_pct", 25)) / 100
                base_p = float(base.get("probability_pct", 55)) / 100
                bear_p = float(bear.get("probability_pct", 20)) / 100
                total_p = bull_p + base_p + bear_p
                if total_p > 0:
                    bull_p /= total_p
                    base_p /= total_p
                    bear_p /= total_p
                ev = (
                    float(bull["price_target"]) * bull_p
                    + float(base["price_target"]) * base_p
                    + float(bear["price_target"]) * bear_p
                )
                ev_pct = (ev - price) / price * 100
                analysis["expected_value"] = round(ev, 2)
                analysis["expected_value_vs_current_pct"] = round(ev_pct, 1)
            except Exception:
                ev_pct = None
        else:
            ev_pct = None

        auto_disq = analysis.get("auto_disqualified", False)
        exclusions = analysis.get("hard_exclusions_triggered") or []
        confidence = float(analysis.get("confidence_score") or 0)

        if auto_disq or [e for e in exclusions if not e.startswith("UNCERTAIN")]:
            allocation, weight = "NONE", "0%"
        elif ev_pct is not None and ev_pct >= 25 and confidence >= 75:
            allocation, weight = "HIGH", "8-12%"
        elif ev_pct is not None and ev_pct >= 15 and confidence >= 60:
            allocation, weight = "MEDIUM", "4-7%"
        elif ev_pct is not None and ev_pct >= 5 and confidence >= 40:
            allocation, weight = "LOW", "2-3%"
        else:
            allocation, weight = "HOLD", "0%"

        analysis["allocation_recommendation"] = allocation
        analysis["suggested_weight_range"] = weight
        return analysis

    def _build_analysis_prompt(
        self,
        data: MarketDataState,
        portfolio_context: Optional[Dict[str, Any]],
        news_analysis: Optional[Dict[str, Any]] = None,
        macro_analysis: Optional[Dict[str, Any]] = None,
        direction_bias: Optional[str] = None,
        quant_models: Optional[Dict[str, Any]] = None,
        pre_exclusions: Optional[List[str]] = None,
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

        quant_section = self._format_quant_models(quant_models) if quant_models else ""

        pre_exclusions_section = ""
        if pre_exclusions:
            flags_text = "\n".join(f"  ⚠ {f}" for f in pre_exclusions)
            pre_exclusions_section = f"""
=== PYTHON PRE-SCREENING FLAGS ===
The following potential Hard Exclusion violations were detected automatically from raw data.
Verify each one. If confirmed → include in hard_exclusions_triggered and set auto_disqualified=true.
If NOT a real violation → explain why in hard_exclusions_triggered as "CLEARED: [reason]".
{flags_text}
"""

        prompt = f"""Perform comprehensive fundamental analysis for {data['symbol']} ({data['exchange']}).
{direction_block}{pre_exclusions_section}
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

=== INSIDER ACTIVITY (SEC Form 4) ===
{self._format_insider_activity(data.get('insider_activity'))}

=== SEC FILINGS ===
{self._format_sec_filings(data.get('sec_filings'))}

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

{quant_section}
{portfolio_section}
=== COMPANY CONTEXT ===
{data.get('company_description', 'No description available.')}

---

Based on ALL the above data and the screener directive, provide your analysis in this exact JSON format:
{{
  "recommendation_type": "BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL",
  "direction_bias": "{direction_bias or 'NEUTRAL'}",
  "confidence_score": 0-100,
  "target_price": <float or null>,
  "stop_loss": <float or null>,
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
  "short_catalysts": ["<catalyst1>"],
  "risk_factors": ["<risk1>", "<risk2>"],
  "catalysts": ["<catalyst1>"],
  "sector_comparison": "<text>",
  "sentiment_cross_check": "<text>",
  "analyst_notes": "<detailed analysis notes>",
  "data_completeness": 0-100,

  "hard_exclusions_triggered": ["<confirmed exclusion or UNCERTAIN/CLEARED: reason>"],
  "auto_disqualified": false,

  "moat_classification": "COST_MONOPOLY|SWITCHING_COST|NETWORK_EFFECT|REGULATORY|NONE",
  "moat_evidence": "<specific quantitative evidence for moat classification>",

  "catalyst_validation": {{
    "primary_catalyst": "<specific named event>",
    "is_specific": true,
    "is_dated": true,
    "expected_date": "<Q1 2026 or DD/MM/YYYY>",
    "is_quantified": true,
    "quantified_impact": "<+X% EPS or +Xx multiple>",
    "is_verifiable": true,
    "not_priced_in": true,
    "catalyst_score": 0
  }},

  "scenario_analysis": {{
    "bull": {{
      "probability_pct": 25,
      "trigger": "<specific event that triggers bull case>",
      "price_target": <float>,
      "timeline_months": 12,
      "upside_pct": <float>
    }},
    "base": {{
      "probability_pct": 55,
      "trigger": "<base case assumption — most likely outcome>",
      "price_target": <float>,
      "timeline_months": 12,
      "upside_pct": <float>
    }},
    "bear": {{
      "probability_pct": 20,
      "trigger": "<specific downside risk that materializes>",
      "price_target": <float>,
      "timeline_months": 12,
      "downside_pct": <float — negative number>
    }}
  }},

  "thesis_breakers": [
    {{"rank": 1, "risk": "<specific risk>", "probability_pct": <float>, "impact_pct": <float — negative>, "risk_adjusted_cost_pct": <probability * impact / 100>}},
    {{"rank": 2, "risk": "<specific risk>", "probability_pct": <float>, "impact_pct": <float — negative>, "risk_adjusted_cost_pct": <probability * impact / 100>}},
    {{"rank": 3, "risk": "<specific risk>", "probability_pct": <float>, "impact_pct": <float — negative>, "risk_adjusted_cost_pct": <probability * impact / 100>}}
  ]
}}

CRITICAL RULES FOR JSON RESPONSE:
- Bull + Base + Bear probability_pct values MUST sum to exactly 100
- If auto_disqualified=true: set recommendation_type="HOLD" and confidence_score below 40
- thesis_breakers ranked by probability_pct × |impact_pct| (highest risk-adjusted cost first)
- Provide empty arrays [] NOT null for list fields when no data is available"""

        return prompt

    @staticmethod
    def _format_insider_activity(insider: Optional[Dict[str, Any]]) -> str:
        if not insider:
            return "Not available (SEC EDGAR)"
        signal = insider.get("signal", "NEUTRAL")
        count = insider.get("transaction_count", 0)
        recents = insider.get("recent_transactions") or []
        lines = [f"Signal: {signal} | Transactions (90d): {count}"]
        for t in recents[:3]:
            lines.append(
                f"  - {t.get('insider_name','?')} ({t.get('officer_title','?')}): "
                f"{t.get('transaction_type','?')} {t.get('shares','?')} shares @ ${t.get('price','?')} "
                f"on {t.get('transaction_date','?')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_sec_filings(sec: Optional[Dict[str, Any]]) -> str:
        if not sec:
            return "Not available (SEC EDGAR)"
        annual = sec.get("latest_annual") or {}
        quarterly = sec.get("latest_quarterly") or {}
        lines = []
        if annual:
            lines.append(f"Latest 10-K: {annual.get('filed','?')} — {annual.get('report_date','?')}")
        if quarterly:
            lines.append(f"Latest 10-Q: {quarterly.get('filed','?')} — {quarterly.get('report_date','?')}")
        if sec.get("has_recent_8k"):
            lines.append("Recent 8-K filing detected (material event)")
        return "\n".join(lines) if lines else "No recent filings found"

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

    @staticmethod
    def _compute_financial_models(data: MarketDataState) -> Dict[str, Any]:
        """Run DCF, DDM, Sensitivity Analysis, Monte Carlo, and Comps purely in Python."""
        models: Dict[str, Any] = {}

        price       = float(data.get("price") or 0)
        pe          = data.get("pe_ratio")
        forward_pe  = data.get("forward_pe")
        pb          = data.get("price_to_book")
        ps          = data.get("price_to_sales")
        beta        = float(data.get("beta") or 1.2)
        fcf         = float(data.get("free_cash_flow") or 0)
        market_cap  = float(data.get("market_cap") or 0)
        rev_growth  = float(data.get("revenue_growth") or 0.05)
        earn_growth = float(data.get("earnings_growth") or 0.05)
        roe         = float(data.get("roe") or 0)
        div_yield   = float(data.get("dividend_yield") or 0)
        sector      = (data.get("sector") or "").lower()

        RISK_FREE        = 0.045
        ERP              = 0.055
        TERMINAL_GROWTH  = 0.025
        beta = max(0.3, min(beta, 3.0))
        ke   = RISK_FREE + beta * ERP  # cost of equity

        # ── DCF ────────────────────────────────────────────────────────────
        try:
            if fcf > 0 and market_cap > 0 and price > 0:
                fcf_g  = min(max(rev_growth, earn_growth, 0.0), 0.30)
                wacc   = ke
                shares = market_cap / price
                # Year-by-year FCF projections
                yearly = []
                fcf_t  = fcf
                pv_fcf = 0.0
                for t in range(1, 6):
                    fcf_t  *= (1 + fcf_g)
                    pv_f    = 1 / (1 + wacc) ** t
                    pv_yr   = fcf_t * pv_f
                    pv_fcf += pv_yr
                    yearly.append({
                        "year": t,
                        "fcf_mm": round(fcf_t / 1e6, 1),
                        "pv_factor": round(pv_f, 4),
                        "pv_mm": round(pv_yr / 1e6, 1),
                    })
                term_value   = fcf_t * (1 + TERMINAL_GROWTH) / (wacc - TERMINAL_GROWTH)
                pv_terminal  = term_value / (1 + wacc) ** 5
                total_equity = pv_fcf + pv_terminal
                intrinsic    = total_equity / shares
                upside       = (intrinsic - price) / price * 100
                models["dcf"] = {
                    "intrinsic_value":     round(intrinsic, 2),
                    "current_price":       round(price, 2),
                    "upside_pct":          round(upside, 1),
                    "wacc_pct":            round(wacc * 100, 1),
                    "fcf_growth_pct":      round(fcf_g * 100, 1),
                    "terminal_growth_pct": round(TERMINAL_GROWTH * 100, 1),
                    "pv_5yr_fcf":          round(pv_fcf, 0),
                    "pv_terminal":         round(pv_terminal, 0),
                    "terminal_value_total": round(term_value, 0),
                    "total_equity":        round(total_equity, 0),
                    "fcf_base_mm":         round(fcf / 1e6, 1),
                    "shares_mm":           round(shares / 1e6, 1),
                    "yearly_projections":  yearly,
                }
            else:
                models["dcf"] = {"skipped": "Negative/zero FCF or missing market cap — DCF not applicable"}
        except Exception as exc:
            models["dcf"] = {"error": str(exc)}

        # ── DDM (Gordon Growth Model) ──────────────────────────────────────
        try:
            if div_yield > 0 and price > 0:
                d0 = price * div_yield
                if roe > 0 and pe and float(pe) > 0:
                    eps     = price / float(pe)
                    payout  = min(max(d0 / eps, 0.0), 0.95) if eps > 0 else 0.5
                    g_ddm   = min(roe * (1 - payout), 0.12)
                else:
                    g_ddm = 0.03
                if ke > g_ddm:
                    intrinsic_ddm = d0 * (1 + g_ddm) / (ke - g_ddm)
                    upside_ddm    = (intrinsic_ddm - price) / price * 100
                    models["ddm"] = {
                        "intrinsic_value":    round(intrinsic_ddm, 2),
                        "current_price":      round(price, 2),
                        "upside_pct":         round(upside_ddm, 1),
                        "dividend_per_share": round(d0, 2),
                        "growth_rate_pct":    round(g_ddm * 100, 1),
                        "cost_of_equity_pct": round(ke * 100, 1),
                    }
                else:
                    models["ddm"] = {"skipped": f"Sustainable growth ({g_ddm:.1%}) ≥ cost of equity ({ke:.1%})"}
            else:
                models["ddm"] = {"skipped": "Non-dividend paying stock — DDM not applicable"}
        except Exception as exc:
            models["ddm"] = {"error": str(exc)}

        # ── Sensitivity Analysis (P/E × EPS-growth grid) ──────────────────
        try:
            eps_base = None
            pe_used  = None
            if pe and float(pe) > 0 and price > 0:
                eps_base = price / float(pe);  pe_used = float(pe)
            elif forward_pe and float(forward_pe) > 0 and price > 0:
                eps_base = price / float(forward_pe);  pe_used = float(forward_pe)

            if eps_base and eps_base > 0:
                pe_multiples   = [12, 15, 18, 20, 22, 25]
                growth_rates   = [-0.10, 0.0, 0.05, 0.10, 0.15, 0.20]
                table: Dict[str, Dict[str, float]] = {}
                for g in growth_rates:
                    row: Dict[str, float] = {}
                    for pe_m in pe_multiples:
                        row[str(pe_m)] = round(eps_base * (1 + g) * pe_m, 2)
                    table[f"{g:+.0%}"] = row
                models["sensitivity"] = {
                    "current_eps":     round(eps_base, 2),
                    "current_pe":      round(pe_used, 1),
                    "current_price":   round(price, 2),
                    "pe_scenarios":    pe_multiples,
                    "growth_scenarios": [f"{g:+.0%}" for g in growth_rates],
                    "table":           table,
                }
            else:
                models["sensitivity"] = {"skipped": "No EPS available (missing P/E) — sensitivity not computed"}
        except Exception as exc:
            models["sensitivity"] = {"error": str(exc)}

        # ── Monte Carlo (GBM, 1 000 paths, 252 days) ──────────────────────
        try:
            if price > 0:
                rng          = np.random.default_rng(seed=42)
                N_SIMS, DAYS = 1_000, 252
                annual_vol   = beta * 0.20
                annual_drift = min(max(rev_growth, 0.0), 0.30)
                daily_drift  = annual_drift / DAYS
                daily_vol    = annual_vol / math.sqrt(DAYS)
                shocks       = rng.normal(daily_drift, daily_vol, (N_SIMS, DAYS))
                finals       = price * np.exp(np.cumsum(shocks, axis=1))[:, -1]
                models["monte_carlo"] = {
                    "current_price":       round(price, 2),
                    "p10":                 round(float(np.percentile(finals, 10)), 2),
                    "p25":                 round(float(np.percentile(finals, 25)), 2),
                    "mean":                round(float(np.mean(finals)), 2),
                    "p75":                 round(float(np.percentile(finals, 75)), 2),
                    "p90":                 round(float(np.percentile(finals, 90)), 2),
                    "prob_above_pct":      round(float(np.mean(finals > price) * 100), 1),
                    "annual_vol_pct":      round(annual_vol * 100, 1),
                    "annual_drift_pct":    round(annual_drift * 100, 1),
                    "simulations":         N_SIMS,
                    "horizon_days":        DAYS,
                }
            else:
                models["monte_carlo"] = {"skipped": "No price available"}
        except Exception as exc:
            models["monte_carlo"] = {"error": str(exc)}

        # ── Comps (Sector Comparable Multiples) ───────────────────────────
        SECTOR_MULTIPLES: Dict[str, Dict[str, float]] = {
            "technology":              {"pe": 28.0, "pb": 7.0,  "ps": 6.0, "ev_ebitda": 22.0},
            "semiconductors":          {"pe": 25.0, "pb": 5.5,  "ps": 5.0, "ev_ebitda": 18.0},
            "software":                {"pe": 35.0, "pb": 8.0,  "ps": 8.0, "ev_ebitda": 28.0},
            "healthcare":              {"pe": 22.0, "pb": 3.5,  "ps": 2.5, "ev_ebitda": 14.0},
            "biotechnology":           {"pe": 40.0, "pb": 5.0,  "ps": 8.0, "ev_ebitda": 30.0},
            "financials":              {"pe": 13.0, "pb": 1.4,  "ps": 2.0, "ev_ebitda": 10.0},
            "banks":                   {"pe": 11.0, "pb": 1.2,  "ps": 2.0, "ev_ebitda":  9.0},
            "consumer discretionary":  {"pe": 22.0, "pb": 4.5,  "ps": 1.8, "ev_ebitda": 14.0},
            "consumer staples":        {"pe": 19.0, "pb": 5.5,  "ps": 1.5, "ev_ebitda": 13.0},
            "energy":                  {"pe": 13.0, "pb": 1.6,  "ps": 1.2, "ev_ebitda":  7.0},
            "utilities":               {"pe": 17.0, "pb": 1.8,  "ps": 1.5, "ev_ebitda": 11.0},
            "industrials":             {"pe": 20.0, "pb": 3.5,  "ps": 1.5, "ev_ebitda": 13.0},
            "real estate":             {"pe": 40.0, "pb": 2.0,  "ps": 6.0, "ev_ebitda": 18.0},
            "communication services":  {"pe": 18.0, "pb": 3.0,  "ps": 2.5, "ev_ebitda": 10.0},
            "materials":               {"pe": 16.0, "pb": 2.2,  "ps": 1.3, "ev_ebitda":  9.0},
        }
        DEFAULT_MULT = {"pe": 20.0, "pb": 3.0, "ps": 2.5, "ev_ebitda": 13.0}

        try:
            sect_key   = next((k for k in SECTOR_MULTIPLES if k in sector or sector in k), None)
            sect_mult  = SECTOR_MULTIPLES.get(sect_key, DEFAULT_MULT) if sect_key else DEFAULT_MULT
            comparisons: Dict[str, Any] = {}

            if pe and float(pe) > 0 and price > 0:
                c_pe   = float(pe)
                s_pe   = sect_mult["pe"]
                eps_c  = price / c_pe
                fair_pe = eps_c * s_pe
                comparisons["pe"] = {
                    "company": round(c_pe, 1), "sector_avg": s_pe,
                    "premium_pct": round((c_pe / s_pe - 1) * 100, 1),
                    "implied_price": round(fair_pe, 2),
                    "upside_pct": round((fair_pe / price - 1) * 100, 1),
                }
            if pb and float(pb) > 0 and price > 0:
                c_pb   = float(pb)
                s_pb   = sect_mult["pb"]
                bvps   = price / c_pb
                fair_pb = bvps * s_pb
                comparisons["pb"] = {
                    "company": round(c_pb, 1), "sector_avg": s_pb,
                    "premium_pct": round((c_pb / s_pb - 1) * 100, 1),
                    "implied_price": round(fair_pb, 2),
                    "upside_pct": round((fair_pb / price - 1) * 100, 1),
                }
            if ps and float(ps) > 0 and price > 0:
                c_ps   = float(ps)
                s_ps   = sect_mult["ps"]
                sps    = price / c_ps
                fair_ps = sps * s_ps
                comparisons["ps"] = {
                    "company": round(c_ps, 1), "sector_avg": s_ps,
                    "premium_pct": round((c_ps / s_ps - 1) * 100, 1),
                    "implied_price": round(fair_ps, 2),
                    "upside_pct": round((fair_ps / price - 1) * 100, 1),
                }

            models["comps"] = {
                "sector": data.get("sector") or "Unknown",
                "matched_key": sect_key or "default",
                "sector_averages": sect_mult,
                "comparisons": comparisons,
            }
        except Exception as exc:
            models["comps"] = {"error": str(exc)}

        return models

    @staticmethod
    def _format_quant_models(models: Dict[str, Any]) -> str:
        """Summarise quantitative model outputs for the LLM prompt."""
        lines = ["=== QUANTITATIVE MODEL OUTPUTS (Python-computed) ==="]

        dcf = models.get("dcf", {})
        if dcf.get("intrinsic_value"):
            lines.append(
                f"DCF Intrinsic Value: ${dcf['intrinsic_value']:.2f} "
                f"({dcf['upside_pct']:+.1f}% vs current) | "
                f"WACC {dcf['wacc_pct']}% | FCF growth {dcf['fcf_growth_pct']}%"
            )
        else:
            lines.append(f"DCF: {dcf.get('skipped') or dcf.get('error', 'N/A')}")

        ddm = models.get("ddm", {})
        if ddm.get("intrinsic_value"):
            lines.append(
                f"DDM (Gordon) Intrinsic Value: ${ddm['intrinsic_value']:.2f} "
                f"({ddm['upside_pct']:+.1f}%) | Div/share ${ddm['dividend_per_share']:.2f} | "
                f"g={ddm['growth_rate_pct']}% | ke={ddm['cost_of_equity_pct']}%"
            )
        else:
            lines.append(f"DDM: {ddm.get('skipped') or ddm.get('error', 'N/A')}")

        mc = models.get("monte_carlo", {})
        if mc.get("mean"):
            lines.append(
                f"Monte Carlo (1 000 sims, 1yr): "
                f"P10=${mc['p10']} | P25=${mc['p25']} | Mean=${mc['mean']} | "
                f"P75=${mc['p75']} | P90=${mc['p90']} | "
                f"Prob>current: {mc['prob_above_pct']}% | "
                f"Vol {mc['annual_vol_pct']}% | Drift {mc['annual_drift_pct']}%"
            )
        else:
            lines.append(f"Monte Carlo: {mc.get('skipped') or mc.get('error', 'N/A')}")

        comps = models.get("comps", {})
        cmp = comps.get("comparisons", {})
        if cmp:
            parts = []
            if "pe" in cmp:
                parts.append(f"P/E {cmp['pe']['company']}x vs {cmp['pe']['sector_avg']}x sector → implied ${cmp['pe']['implied_price']} ({cmp['pe']['upside_pct']:+.1f}%)")
            if "pb" in cmp:
                parts.append(f"P/B {cmp['pb']['company']}x vs {cmp['pb']['sector_avg']}x → implied ${cmp['pb']['implied_price']} ({cmp['pb']['upside_pct']:+.1f}%)")
            if "ps" in cmp:
                parts.append(f"P/S {cmp['ps']['company']}x vs {cmp['ps']['sector_avg']}x → implied ${cmp['ps']['implied_price']} ({cmp['ps']['upside_pct']:+.1f}%)")
            lines.append(f"Comps vs {comps.get('sector', '?')} sector: " + " | ".join(parts))
        else:
            lines.append(f"Comps: {comps.get('error', 'N/A')}")

        sens = models.get("sensitivity", {})
        if "current_eps" in sens:
            lines.append(
                f"Sensitivity (EPS ${sens['current_eps']} × P/E grid): "
                f"e.g. at 0% growth → P/E 15={sens['table'].get('0%', {}).get('15', 'N/A')} | "
                f"P/E 20={sens['table'].get('0%', {}).get('20', 'N/A')} | "
                f"P/E 25={sens['table'].get('0%', {}).get('25', 'N/A')}"
            )

        lines.append(
            "\nUse these models as DATA POINTS to calibrate your valuation assessment and "
            "target price. Reference the most relevant models in analyst_notes."
        )
        return "\n".join(lines)

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

        # Enforce auto_disqualified → HOLD
        if analysis.get("auto_disqualified"):
            analysis["recommendation_type"] = "HOLD"
            if float(analysis["confidence_score"]) > 40:
                analysis["confidence_score"] = 30.0

        # Validate moat classification
        valid_moats = {"COST_MONOPOLY", "SWITCHING_COST", "NETWORK_EFFECT", "REGULATORY", "NONE"}
        if analysis.get("moat_classification") not in valid_moats:
            analysis["moat_classification"] = "NONE"

        # Ensure thesis_breakers is a list
        if not isinstance(analysis.get("thesis_breakers"), list):
            analysis["thesis_breakers"] = []

        # Ensure hard_exclusions_triggered is a list
        if not isinstance(analysis.get("hard_exclusions_triggered"), list):
            analysis["hard_exclusions_triggered"] = []

        # Compute Expected Value + Allocation recommendation from scenario analysis
        price = float(data.get("price") or 0)
        analysis = self._compute_ev_and_allocation(analysis, price)

        analysis["symbol"] = data["symbol"]
        analysis["direction_bias"] = direction_bias or "NEUTRAL"
        analysis["analysis_timestamp"] = datetime.now(timezone.utc).isoformat()
        analysis["analyst_id"] = "fundamental_agent_v1"

        return analysis

    def _fallback_analysis(self, data: MarketDataState, error: str, quant_models: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            "hard_exclusions_triggered": [],
            "auto_disqualified": False,
            "moat_classification": "NONE",
            "moat_evidence": "N/A",
            "catalyst_validation": {"catalyst_score": 0},
            "scenario_analysis": {},
            "thesis_breakers": [],
            "expected_value": None,
            "expected_value_vs_current_pct": None,
            "allocation_recommendation": "HOLD",
            "suggested_weight_range": "0%",
            "symbol": data["symbol"],
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "analyst_id": "fundamental_agent_v1",
            "error": error,
            "quantitative_models": quant_models or {},
        }


_fundamental_agent: Optional[FundamentalAnalystAgent] = None


def get_fundamental_agent() -> FundamentalAnalystAgent:
    global _fundamental_agent
    if _fundamental_agent is None:
        _fundamental_agent = FundamentalAnalystAgent()
    return _fundamental_agent
