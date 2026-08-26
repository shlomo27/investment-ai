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

    async def send_message(self, text: str, parse_mode: str = "HTML",
                           chat_id: Optional[str] = None) -> bool:
        target = chat_id or self._chat_id
        if not (self._bot_token and not self._bot_token.startswith("your_") and target):
            logger.debug("Telegram skipped — not configured")
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.BASE_URL}/bot{self._bot_token}/sendMessage",
                    json={
                        "chat_id": target,
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

    async def send_admin_alert(self, text: str, dedup_hours: int = 6) -> bool:
        """Send an operational alert to the ADMIN channel (not the public one).
        Falls back to the public channel if no admin chat id is configured.

        Identical alerts are suppressed for dedup_hours. An outage that lasts a
        day — Claude out of credits, a provider down — is re-detected on every
        scheduled run, and each detection sent the same message again: the same
        five paragraphs every thirty minutes, until the channel was unreadable
        and the alert that actually mattered was buried among its own repeats.
        Pass dedup_hours=0 for an alert that must always go out.
        """
        admin_chat = settings.TELEGRAM_ADMIN_CHAT_ID or self._chat_id

        if dedup_hours > 0:
            import hashlib

            key = ("investment_ai:admin_alert_sent:"
                   + hashlib.sha256(text.encode("utf-8")).hexdigest()[:32])
            try:
                import redis.asyncio as aioredis

                client = aioredis.from_url(settings.REDIS_URL)
                try:
                    # SET NX: only the first sender in the window wins.
                    fresh = await client.set(key, "1", ex=dedup_hours * 3600, nx=True)
                finally:
                    await client.aclose()
                if not fresh:
                    logger.info("Admin alert suppressed as a repeat", preview=text[:60])
                    return True
            except Exception:
                pass  # de-duplication is a convenience — never drop an alert over it

        return await self.send_message(text, chat_id=admin_chat)

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
