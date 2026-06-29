"""
Telegram Bot Notification Service
Sends investment alerts to a configured Telegram chat.
"""
import httpx
from typing import Optional
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


class TelegramService:
    BASE_URL = "https://api.telegram.org"

    def __init__(self):
        self._bot_token = settings.TELEGRAM_BOT_TOKEN
        self._chat_id = settings.TELEGRAM_CHAT_ID

    def is_configured(self) -> bool:
        return bool(
            self._bot_token
            and self._chat_id
            and not self._bot_token.startswith("your_")
        )

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.is_configured():
            logger.debug("Telegram skipped — not configured")
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/bot{self._bot_token}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                )
                if resp.status_code == 200:
                    logger.debug("Telegram message sent")
                    return True
                logger.warning("Telegram send failed", status=resp.status_code)
                return False
        except Exception as e:
            logger.warning("Telegram notification failed", error=str(e))
            return False

    async def send_investment_alert(
        self,
        symbol: str,
        rec_type: str,
        confidence: float,
        language: str = "he",
    ) -> bool:
        if language == "he":
            direction = "קנייה" if "BUY" in rec_type else "מכירה" if "SELL" in rec_type else "המתנה"
            strength = " חזקה" if "STRONG" in rec_type else ""
            text = (
                f"🤖 <b>InvestAI — סיגנל {direction}{strength}</b>\n\n"
                f"📊 <b>מניה:</b> <code>{symbol}</code>\n"
                f"📈 <b>המלצה:</b> {rec_type}\n"
                f"🎯 <b>ביטחון:</b> {confidence:.0f}%\n\n"
                f"⚠️ כנס למערכת לצפייה בניתוח המלא"
            )
        else:
            text = (
                f"🤖 <b>InvestAI Signal</b>\n\n"
                f"📊 <b>Symbol:</b> <code>{symbol}</code>\n"
                f"📈 <b>Recommendation:</b> {rec_type}\n"
                f"🎯 <b>Confidence:</b> {confidence:.0f}%\n\n"
                f"⚠️ Login to view full analysis"
            )
        return await self.send_message(text)

    async def send_test_message(self) -> bool:
        return await self.send_message(
            "🧪 <b>InvestAI — Telegram מחובר בהצלחה!</b>\n\nתקבל כאן התראות השקעה בזמן אמת."
        )


_telegram_service: Optional[TelegramService] = None


def get_telegram_service() -> TelegramService:
    global _telegram_service
    if _telegram_service is None:
        _telegram_service = TelegramService()
    return _telegram_service
