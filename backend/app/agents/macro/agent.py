"""
Macro Context Agent — Gemini
Broad macro and sector context using Google Gemini.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import structlog

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.agents.state import MarketDataState

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a macro and sector research analyst with deep expertise in global markets.
You provide broad market context that complements detailed fundamental analysis.

You analyze:
1. Sector rotation trends — is this sector gaining or losing institutional favor?
2. Macro environment — interest rates, inflation, GDP trends affecting this stock
3. Competitive landscape — market position vs peers
4. Regulatory environment — current or pending regulations
5. Global market factors — how international events affect this stock
6. Analyst consensus trends — are analysts upgrading or downgrading this sector?

Use your training knowledge about markets, sectors, and macroeconomics.
Output must be strict JSON."""


class MacroContextAgent:
    def __init__(self):
        self._llm = None

    def _get_llm(self):
        if not settings.GEMINI_API_KEY:
            return None
        if self._llm is None:
            self._llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=settings.GEMINI_API_KEY,
                max_output_tokens=1500,
                temperature=0.1,
            )
        return self._llm

    async def analyze(self, market_data: MarketDataState) -> Dict[str, Any]:
        symbol = market_data["symbol"]
        sector = market_data.get("sector", "Unknown")

        logger.info("MacroContextAgent starting", symbol=symbol, sector=sector)

        llm = self._get_llm()
        if llm is None:
            logger.warning("Gemini unavailable, skipping macro analysis", symbol=symbol)
            return self._empty_analysis(symbol, "GEMINI_API_KEY not configured")

        prompt = self._build_prompt(market_data)

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

            logger.info(
                "MacroContextAgent completed",
                symbol=symbol,
                sector_outlook=result.get("sector_outlook"),
                macro_impact=result.get("macro_impact_on_stock"),
            )
            return result

        except json.JSONDecodeError as e:
            logger.error("JSON parse error in macro analysis", error=str(e))
            return self._empty_analysis(symbol, f"JSON parse error: {e}")
        except Exception as e:
            logger.error("Macro analysis failed", symbol=symbol, error=str(e))
            return self._empty_analysis(symbol, str(e))

    @staticmethod
    def _v(value: Any, default: Any = "N/A") -> Any:
        return value if value is not None else default

    def _build_prompt(self, data: MarketDataState) -> str:
        v = self._v
        description = data.get("company_description") or ""
        return f"""Provide macro and sector context for {data['symbol']} ({data.get('exchange', 'US')}).

Company overview: {description[:300] if description else 'N/A'}
Sector: {v(data.get('sector'), 'Unknown')}
Industry: {v(data.get('industry'), 'Unknown')}
Country: {v(data.get('country'), 'US')}
Market Cap: ${v(data.get('market_cap'), 0):,.0f}
Beta: {v(data.get('beta'), 'N/A')}
Revenue Growth YoY: {v(data.get('revenue_growth'), 'N/A')}

Respond ONLY with valid JSON:
{{
  "sector_outlook": "POSITIVE|NEUTRAL|NEGATIVE",
  "sector_trend": "<1-2 sentences on sector rotation and institutional flows>",
  "macro_environment": "<1-2 sentences on macro factors: rates, inflation, growth>",
  "macro_impact_on_stock": "TAILWIND|NEUTRAL|HEADWIND",
  "competitive_position": "LEADER|STRONG|AVERAGE|WEAK",
  "competitive_notes": "<1-2 sentences on competitive landscape>",
  "regulatory_risk": "LOW|MEDIUM|HIGH",
  "regulatory_notes": "<any relevant regulatory issues>",
  "global_factors": "<relevant international/geopolitical factors>",
  "analyst_consensus_trend": "UPGRADING|STABLE|DOWNGRADING",
  "key_macro_risks": ["<risk1>", "<risk2>"],
  "key_macro_catalysts": ["<catalyst1>", "<catalyst2>"],
  "macro_confidence": 0-100
}}"""

    def _empty_analysis(self, symbol: str, reason: str) -> Dict[str, Any]:
        return {
            "sector_outlook": "NEUTRAL",
            "sector_trend": "Macro analysis unavailable",
            "macro_environment": "N/A",
            "macro_impact_on_stock": "NEUTRAL",
            "competitive_position": "AVERAGE",
            "competitive_notes": "N/A",
            "regulatory_risk": "MEDIUM",
            "regulatory_notes": "N/A",
            "global_factors": "N/A",
            "analyst_consensus_trend": "STABLE",
            "key_macro_risks": [],
            "key_macro_catalysts": [],
            "macro_confidence": 0,
            "symbol": symbol,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "skipped_reason": reason,
        }


_macro_agent: Optional[MacroContextAgent] = None


def get_macro_agent() -> MacroContextAgent:
    global _macro_agent
    if _macro_agent is None:
        _macro_agent = MacroContextAgent()
    return _macro_agent
