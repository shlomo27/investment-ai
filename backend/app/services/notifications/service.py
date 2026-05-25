"""
Multi-Channel Notification Service
Sends generic external alerts (push/SMS/email) and stores full details internally.
External message is always generic - full AI analysis only visible after login.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.models.notification import Notification, NotificationType
from app.db.models.user import User

logger = structlog.get_logger(__name__)

EXTERNAL_MESSAGE_HE = "יש לך עדכון השקעות חדש. אנא היכנס למערכת לצפייה בפרטים."
EXTERNAL_MESSAGE_EN = "You have a new investment update. Please log in to view details."


class NotificationService:
    """
    Sends multi-channel notifications to users.
    Critical design: external channels get ONLY the generic message.
    Full AI analysis details are ONLY accessible through the authenticated app.
    """

    def __init__(self):
        self._firebase_app = None
        self._twilio_client = None
        self._sendgrid_client = None

    async def send_notification(
        self,
        user_id: int,
        recommendation_id: Optional[int],
        internal_detail: Dict[str, Any],
        db: AsyncSession,
        notification_type: NotificationType = NotificationType.RECOMMENDATION,
        title: Optional[str] = None,
    ) -> Optional[Notification]:
        """
        Main method: creates notification record and sends via all enabled channels.
        External channels receive only the generic message.
        """
        try:
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()

            if not user or not user.is_active:
                return None

            # Use language preference for external message
            external_msg = (
                EXTERNAL_MESSAGE_HE if user.preferred_language == "he"
                else EXTERNAL_MESSAGE_EN
            )

            notification = Notification(
                user_id=user_id,
                recommendation_id=recommendation_id,
                notification_type=notification_type,
                external_message=external_msg,
                internal_detail=internal_detail,
                title=title or "עדכון השקעות" if user.preferred_language == "he" else "Investment Update",
                channels_sent=[],
                is_read=False,
                sent_at=datetime.now(timezone.utc),
            )
            db.add(notification)
            await db.flush()

            channels_sent: List[str] = []

            # Send push notification
            if user.notification_push and user.push_token:
                success = await self._send_push(
                    push_token=user.push_token,
                    title=notification.title,
                    body=external_msg,
                )
                if success:
                    channels_sent.append("push")

            # Send SMS
            if user.notification_sms and user.phone:
                success = await self._send_sms(
                    phone=user.phone,
                    message=external_msg,
                )
                if success:
                    channels_sent.append("sms")

            # Send email
            if user.notification_email and user.email:
                success = await self._send_email(
                    email=user.email,
                    name=user.full_name,
                    subject="Investment Update" if user.preferred_language != "he" else "עדכון השקעות",
                    body=external_msg,
                )
                if success:
                    channels_sent.append("email")

            notification.channels_sent = channels_sent
            await db.flush()

            logger.info(
                "Notification sent",
                user_id=user_id,
                notification_id=notification.id,
                channels=channels_sent,
            )

            return notification

        except Exception as e:
            logger.error("send_notification failed", user_id=user_id, error=str(e))
            return None

    async def mark_as_read(
        self, notification_id: int, user_id: int, db: AsyncSession
    ) -> bool:
        """Mark a notification as read."""
        try:
            result = await db.execute(
                select(Notification).where(
                    Notification.id == notification_id,
                    Notification.user_id == user_id,
                )
            )
            notification = result.scalar_one_or_none()
            if not notification:
                return False

            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            await db.flush()
            return True

        except Exception as e:
            logger.error("mark_as_read failed", notification_id=notification_id, error=str(e))
            return False

    async def _send_push(self, push_token: str, title: str, body: str) -> bool:
        """Send Firebase Cloud Messaging push notification."""
        try:
            if not settings.FIREBASE_CREDENTIALS_PATH:
                return False

            import firebase_admin
            from firebase_admin import credentials, messaging

            if not firebase_admin._apps:
                try:
                    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                    firebase_admin.initialize_app(cred)
                    self._firebase_app = firebase_admin.get_app()
                except Exception as e:
                    logger.warning("Firebase init failed", error=str(e))
                    return False

            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                token=push_token,
                data={
                    "type": "investment_update",
                    "action": "open_app",
                },
            )

            import asyncio
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: messaging.send(message)
            )
            logger.debug("Push sent", message_id=response)
            return True

        except Exception as e:
            logger.warning("Push notification failed", error=str(e))
            return False

    async def _send_sms(self, phone: str, message: str) -> bool:
        """Send SMS via Twilio."""
        try:
            if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
                return False

            from twilio.rest import Client
            import asyncio

            def _send():
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                return client.messages.create(
                    body=message,
                    from_=settings.TWILIO_FROM_NUMBER,
                    to=phone,
                )

            msg = await asyncio.get_event_loop().run_in_executor(None, _send)
            logger.debug("SMS sent", sid=msg.sid)
            return True

        except Exception as e:
            logger.warning("SMS notification failed", error=str(e))
            return False

    async def _send_email(
        self,
        email: str,
        name: str,
        subject: str,
        body: str,
    ) -> bool:
        """Send email via SendGrid."""
        try:
            if not settings.SENDGRID_API_KEY:
                return False

            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail
            import asyncio

            message = Mail(
                from_email=(settings.SENDGRID_FROM_EMAIL, settings.SENDGRID_FROM_NAME),
                to_emails=email,
                subject=subject,
                html_content=f"""
                <html>
                <body dir="auto">
                <p>שלום {name},</p>
                <p>{body}</p>
                <p>
                    <a href="http://localhost:3000" style="
                        background-color: #1a73e8;
                        color: white;
                        padding: 12px 24px;
                        text-decoration: none;
                        border-radius: 4px;
                        display: inline-block;
                        margin-top: 16px;
                    ">
                        כניסה למערכת / Login
                    </a>
                </p>
                <p style="color: #888; font-size: 12px;">
                    Investment AI | אל תגיב להודעה זו
                </p>
                </body>
                </html>
                """,
            )

            def _send():
                sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
                return sg.send(message)

            response = await asyncio.get_event_loop().run_in_executor(None, _send)
            logger.debug("Email sent", status=response.status_code, to=email)
            return response.status_code in (200, 201, 202)

        except Exception as e:
            logger.warning("Email notification failed", error=str(e))
            return False

    async def send_system_notification(
        self,
        user_id: int,
        message: str,
        db: AsyncSession,
        title: str = "System Alert",
    ) -> Optional[Notification]:
        """Send a system-level notification (not investment related)."""
        return await self.send_notification(
            user_id=user_id,
            recommendation_id=None,
            internal_detail={"message": message, "type": "SYSTEM"},
            db=db,
            notification_type=NotificationType.SYSTEM,
            title=title,
        )


_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
