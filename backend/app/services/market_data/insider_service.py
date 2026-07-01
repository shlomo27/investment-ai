"""
Insider Trading Service
Fetches SEC Form 4 filings (insider buy/sell) from EDGAR.
Free API — no key required. Rate limit: ~10 req/sec.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import structlog
import httpx

logger = structlog.get_logger(__name__)

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_HEADERS = {"User-Agent": "InvestmentAI research@investment-ai.app"}


class InsiderService:
    def __init__(self):
        self._timeout = httpx.Timeout(15.0)

    async def get_insider_transactions(
        self, symbol: str, days_back: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent Form 4 insider transactions for a symbol from SEC EDGAR.
        Returns list of transaction dicts sorted by date descending.
        """
        from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=EDGAR_HEADERS) as client:
                resp = await client.get(
                    EDGAR_SEARCH_URL,
                    params={
                        "q": f'"{symbol}"',
                        "forms": "4",
                        "dateRange": "custom",
                        "startdt": from_date,
                        "enddt": to_date,
                        "_source": "file_date,period_of_report,display_names,form_type",
                        "hits.hits.total.value": 1,
                        "hits.hits._source.period_of_report": 1,
                    },
                )
                if resp.status_code != 200:
                    logger.debug("EDGAR Form 4 returned non-200", status=resp.status_code, symbol=symbol)
                    return []

                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])

                transactions = []
                for hit in hits[:20]:
                    src = hit.get("_source", {})
                    display_names = src.get("display_names", [])
                    filer = display_names[0] if display_names else "Unknown"

                    transactions.append({
                        "filer": filer,
                        "form_type": src.get("form_type", "4"),
                        "file_date": src.get("file_date", ""),
                        "period_of_report": src.get("period_of_report", ""),
                        "accession_no": hit.get("_id", ""),
                    })

                return transactions

        except Exception as e:
            logger.debug("Insider fetch failed", symbol=symbol, error=str(e))
            return []

    async def get_insider_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Returns a summary of insider activity for the given symbol over the past 90 days.
        """
        transactions = await self.get_insider_transactions(symbol)
        if not transactions:
            return {
                "symbol": symbol,
                "transaction_count": 0,
                "recent_filings": [],
                "signal": "NEUTRAL",
                "days_back": 90,
            }

        recent = transactions[:5]
        count = len(transactions)

        signal = "NEUTRAL"
        if count >= 5:
            signal = "ACTIVE_INSIDER_FILING"
        elif count >= 2:
            signal = "SOME_INSIDER_FILING"

        return {
            "symbol": symbol,
            "transaction_count": count,
            "recent_filings": recent,
            "signal": signal,
            "days_back": 90,
        }


_insider_service: Optional[InsiderService] = None


def get_insider_service() -> InsiderService:
    global _insider_service
    if _insider_service is None:
        _insider_service = InsiderService()
    return _insider_service
