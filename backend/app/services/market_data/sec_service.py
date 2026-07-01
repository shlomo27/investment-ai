"""
SEC EDGAR Service
Fetches recent 10-K and 10-Q filing metadata from SEC EDGAR.
Free API — no key required.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import structlog
import httpx

logger = structlog.get_logger(__name__)

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_HEADERS = {"User-Agent": "InvestmentAI research@investment-ai.app"}


class SECService:
    def __init__(self):
        self._timeout = httpx.Timeout(15.0)

    async def get_recent_filings(
        self, symbol: str, forms: str = "10-K,10-Q", days_back: int = 365
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent annual/quarterly report metadata from SEC EDGAR.
        Returns list of filing metadata dicts.
        """
        from_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=EDGAR_HEADERS) as client:
                resp = await client.get(
                    EDGAR_SEARCH_URL,
                    params={
                        "q": f'"{symbol}"',
                        "forms": forms,
                        "dateRange": "custom",
                        "startdt": from_date,
                        "enddt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    },
                )
                if resp.status_code != 200:
                    return []

                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])

                filings = []
                for hit in hits[:10]:
                    src = hit.get("_source", {})
                    filings.append({
                        "form_type": src.get("form_type", ""),
                        "file_date": src.get("file_date", ""),
                        "period_of_report": src.get("period_of_report", ""),
                        "display_names": src.get("display_names", []),
                        "accession_no": hit.get("_id", ""),
                        "edgar_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={symbol}&type={src.get('form_type', '10-K')}&dateb=&owner=include&count=10",
                    })

                return filings

        except Exception as e:
            logger.debug("SEC EDGAR fetch failed", symbol=symbol, error=str(e))
            return []

    async def get_filings_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Returns a summary of recent SEC filings for the given symbol.
        """
        filings = await self.get_recent_filings(symbol)
        annual = [f for f in filings if f["form_type"] == "10-K"]
        quarterly = [f for f in filings if f["form_type"] == "10-Q"]

        latest_annual = annual[0] if annual else None
        latest_quarterly = quarterly[0] if quarterly else None

        return {
            "symbol": symbol,
            "total_filings": len(filings),
            "latest_annual": latest_annual,
            "latest_quarterly": latest_quarterly,
            "recent_filings": filings[:5],
            "has_recent_filings": len(filings) > 0,
        }


_sec_service: Optional[SECService] = None


def get_sec_service() -> SECService:
    global _sec_service
    if _sec_service is None:
        _sec_service = SECService()
    return _sec_service
