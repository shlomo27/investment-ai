"""
Macro Context Agent — Gemini
Broad macro and sector context using Google Gemini + real-time FRED data.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import structlog

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.agents.state import MarketDataState

logger = structlog.get_logger(__name__)


async def _fetch_fred_series(client: httpx.AsyncClient, series_id: str) -> Optional[float]:
    """Fetch latest value from FRED public CSV endpoint."""
    try:
        resp = await client.get(
            f"https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        lines = [l for l in resp.text.strip().split("\n") if l and not l.startswith("DATE")]
        for line in reversed(lines):
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() not in (".", ""):
                return float(parts[1].strip())
    except Exception:
        pass
    return None


async def _fetch_fear_greed(client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    """Fetch CNN Fear & Greed Index (0=extreme fear, 100=extreme greed)."""
    try:
        resp = await client.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            data = resp.json()
            fg = data.get("fear_and_greed", {})
            score = fg.get("score")
            rating = fg.get("rating", "")
            if score is not None:
                return {"score": round(float(score), 1), "rating": rating}
    except Exception:
        pass
    return None


async def fetch_realtime_macro() -> Dict[str, Any]:
    """
    Fetch current US macro indicators from FRED + CNN Fear & Greed (all free, no key).
    Returns a dict with latest values.
    """
    result: Dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            fred_tasks = [
                _fetch_fred_series(client, "FEDFUNDS"),   # Fed Funds Rate
                _fetch_fred_series(client, "DGS10"),       # 10Y Treasury
                _fetch_fred_series(client, "UNRATE"),      # Unemployment rate
                _fetch_fear_greed(client),                 # CNN Fear & Greed
            ]
            fed_rate, ten_yr, unemployment, fear_greed = await asyncio.gather(
                *fred_tasks, return_exceptions=True
            )

            if isinstance(fed_rate, float):
                result["fed_funds_rate_pct"] = round(fed_rate, 2)
            if isinstance(ten_yr, float):
                result["ten_year_treasury_pct"] = round(ten_yr, 2)
            if isinstance(unemployment, float):
                result["unemployment_rate_pct"] = round(unemployment, 2)
            if isinstance(fear_greed, dict) and fear_greed:
                result["fear_greed_score"] = fear_greed["score"]
                result["fear_greed_rating"] = fear_greed["rating"]

            # CPI YoY: fetch last 14 months and compute
            try:
                resp = await client.get(
                    "https://fred.stlouisfed.org/graph/fredgraph.csv",
                    params={"id": "CPIAUCSL"},
                    timeout=8,
                )
                if resp.status_code == 200:
                    lines = [l for l in resp.text.strip().split("\n")
                             if l and not l.startswith("DATE")]
                    valid = [(l.split(",")[0], float(l.split(",")[1]))
                             for l in lines if len(l.split(",")) == 2
                             and l.split(",")[1].strip() not in (".", "")]
                    if len(valid) >= 13:
                        cpi_yoy = (valid[-1][1] - valid[-13][1]) / valid[-13][1] * 100
                        result["cpi_yoy_pct"] = round(cpi_yoy, 2)
            except Exception:
                pass

    except Exception as e:
        logger.debug("Real-time macro fetch failed", error=str(e))

    return result


async def fetch_israeli_macro() -> Dict[str, Any]:
    """
    Fetch Israeli macro indicators from FRED (free, no key required).
    Self-contained — opens its own httpx client, matching fetch_realtime_macro().
    FRED series:
      INTDSRILM193N    — Bank of Israel benchmark interest rate
      DEXILAS          — USD/ILS spot exchange rate (daily)
      ISRPCPIALLAINMEI — Israel CPI all items (YoY computed)
    """
    result: Dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            boi_rate, usd_ils = await asyncio.gather(
                _fetch_fred_series(client, "INTDSRILM193N"),
                _fetch_fred_series(client, "DEXILAS"),
                return_exceptions=True,
            )
        il_cpi = await asyncio.to_thread(_fetch_fred_cpi_series_sync, "ISRPCPIALLAINMEI")
        if isinstance(boi_rate, float):
            result["boi_interest_rate_pct"] = round(boi_rate, 2)
        if isinstance(usd_ils, float):
            result["usd_ils_rate"] = round(usd_ils, 4)
        if isinstance(il_cpi, float):
            result["il_cpi_yoy_pct"] = round(il_cpi, 2)
    except Exception as e:
        logger.debug("Israeli macro fetch failed", error=str(e))
    return result


def _fetch_fred_cpi_series_sync(series_id: str) -> Optional[float]:
    """Synchronous CPI YoY computation — run in thread pool."""
    import requests as _req
    try:
        resp = _req.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv",
            params={"id": series_id},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        lines = [l for l in resp.text.strip().split("\n") if l and not l.startswith("DATE")]
        valid = []
        for line in lines:
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() not in (".", ""):
                try:
                    valid.append(float(parts[1].strip()))
                except ValueError:
                    pass
        if len(valid) >= 13:
            return (valid[-1] - valid[-13]) / valid[-13] * 100
    except Exception:
        pass
    return None

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
        api_key = settings.GEMINI_API_KEY or settings.GOOGLE_AI_API_KEY
        if not api_key:
            return None
        if self._llm is None:
            self._llm = ChatGoogleGenerativeAI(
                model=settings.GEMINI_MODEL,
                google_api_key=api_key,
                max_output_tokens=1500,
                temperature=0.1,
            )
        return self._llm

    async def analyze(self, market_data: MarketDataState) -> Dict[str, Any]:
        symbol = market_data["symbol"]
        sector = market_data.get("sector", "Unknown")
        is_israeli = market_data.get("country", "US") == "IL" or str(market_data.get("exchange", "")).upper() == "TASE"

        logger.info("MacroContextAgent starting", symbol=symbol, sector=sector, is_israeli=is_israeli)

        llm = self._get_llm()
        if llm is None:
            logger.warning("Gemini unavailable, skipping macro analysis", symbol=symbol)
            return self._empty_analysis(symbol, "GEMINI_API_KEY not configured")

        # Fetch macro data: always US, add Israeli data for TASE stocks.
        # Both functions are self-contained and open their own httpx clients.
        tasks = [fetch_realtime_macro()]
        if is_israeli:
            tasks.append(fetch_israeli_macro())
        results = await asyncio.gather(*tasks, return_exceptions=True)

        realtime_macro: Dict[str, Any] = results[0] if isinstance(results[0], dict) else {}
        israeli_macro: Dict[str, Any] = results[1] if is_israeli and isinstance(results[1], dict) else {}

        logger.debug("Macro fetched", us=realtime_macro, israeli=israeli_macro)
        prompt = self._build_prompt(market_data, realtime_macro, israeli_macro if is_israeli else None)

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
            result["realtime_macro"] = realtime_macro
            if israeli_macro:
                result["israeli_macro"] = israeli_macro
            parts = []
            if realtime_macro:
                if "fed_funds_rate_pct" in realtime_macro:
                    parts.append(f"Fed Rate: {realtime_macro['fed_funds_rate_pct']}%")
                if "ten_year_treasury_pct" in realtime_macro:
                    parts.append(f"10Y Treasury: {realtime_macro['ten_year_treasury_pct']}%")
                if "cpi_yoy_pct" in realtime_macro:
                    parts.append(f"CPI YoY: {realtime_macro['cpi_yoy_pct']}%")
                if "unemployment_rate_pct" in realtime_macro:
                    parts.append(f"Unemployment: {realtime_macro['unemployment_rate_pct']}%")
                if "fear_greed_score" in realtime_macro:
                    parts.append(f"Fear&Greed: {realtime_macro['fear_greed_score']}/100 ({realtime_macro.get('fear_greed_rating', '')})")
            if israeli_macro:
                if "boi_interest_rate_pct" in israeli_macro:
                    parts.append(f"BoI Rate: {israeli_macro['boi_interest_rate_pct']}%")
                if "usd_ils_rate" in israeli_macro:
                    parts.append(f"USD/ILS: {israeli_macro['usd_ils_rate']}")
                if "il_cpi_yoy_pct" in israeli_macro:
                    parts.append(f"IL CPI YoY: {israeli_macro['il_cpi_yoy_pct']}%")
            if parts:
                result["real_time_macro_summary"] = " | ".join(parts)

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

    def _build_prompt(self, data: MarketDataState, realtime_macro: Optional[Dict[str, Any]] = None,
                      israeli_macro: Optional[Dict[str, Any]] = None) -> str:
        v = self._v
        description = data.get("company_description") or ""
        rt = realtime_macro or {}
        il = israeli_macro or {}
        macro_data_section = ""
        if rt:
            fg = rt.get('fear_greed_score')
            fg_label = rt.get('fear_greed_rating', '')
            fg_str = f"{fg}/100 ({fg_label})" if fg is not None else "N/A"
            macro_data_section = f"""
=== LIVE US MACRO DATA (Current, from FRED + CNN) ===
Fed Funds Rate: {rt.get('fed_funds_rate_pct', 'N/A')}%
10-Year Treasury Yield: {rt.get('ten_year_treasury_pct', 'N/A')}%
CPI Inflation YoY: {rt.get('cpi_yoy_pct', 'N/A')}%
Unemployment Rate: {rt.get('unemployment_rate_pct', 'N/A')}%
CNN Fear & Greed Index: {fg_str}  (0=Extreme Fear, 50=Neutral, 100=Extreme Greed)
Use this LIVE data — do NOT rely on training knowledge for these indicators.
"""

        israeli_section = ""
        if il:
            israeli_section = f"""
=== LIVE ISRAELI MACRO DATA (Current, from FRED) ===
Bank of Israel Benchmark Rate: {il.get('boi_interest_rate_pct', 'N/A')}%
USD/ILS Exchange Rate: {il.get('usd_ils_rate', 'N/A')} (shekel per dollar)
Israel CPI Inflation YoY: {il.get('il_cpi_yoy_pct', 'N/A')}%
Use this LIVE data for Israeli macro context — consider geopolitical risks, BoI policy,
shekel strength/weakness, and correlation with US rates.
"""

        country = data.get('country', 'US')
        is_tase = country == 'IL' or str(data.get('exchange', '')).upper() == 'TASE'
        market_context = (
            "This is an ISRAELI company listed on the Tel Aviv Stock Exchange (TASE). "
            "Analyze macro context from both the Israeli economy AND global/US market impact on Israel."
            if is_tase else
            "Analyze macro context from US and global markets."
        )

        return f"""Provide macro and sector context for {data['symbol']} ({data.get('exchange', 'US')}).

{market_context}
Company overview: {description[:300] if description else 'N/A'}
Sector: {v(data.get('sector'), 'Unknown')}
Industry: {v(data.get('industry'), 'Unknown')}
Country: {country}
Market Cap: {v(data.get('market_cap'), 0):,.0f} {'ILS' if is_tase else 'USD'}
Beta: {v(data.get('beta'), 'N/A')}
Revenue Growth YoY: {v(data.get('revenue_growth'), 'N/A')}
{macro_data_section}{israeli_section}

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
