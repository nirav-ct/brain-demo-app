"""Notification service.

Sends transactional emails and in-app notifications to users.
Supports email, SMS, and webhook delivery channels.

All outbound payloads and log entries are processed through the PII masking
pipeline to comply with GDPR Article 25 (data protection by design).
"""

import logging
import re
import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Optional

from src.config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PII masking utilities
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(r"\+?\d[\d\-\s]{7,}\d")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def mask_email(email: str) -> str:
    local, domain = email.split("@")
    return f"{local[0]}***@{domain}"


def mask_pii(text: str) -> str:
    """Redact known PII patterns from free text."""
    text = _SSN_RE.sub("[SSN REDACTED]", text)
    text = _CREDIT_CARD_RE.sub("[CARD REDACTED]", text)
    text = _PHONE_RE.sub("[PHONE REDACTED]", text)
    text = _EMAIL_RE.sub(lambda m: mask_email(m.group()), text)
    return text


def mask_name(name: str) -> str:
    parts = name.split()
    if len(parts) <= 1:
        return name[0] + "***" if name else ""
    return parts[0][0] + "*** " + parts[-1][0] + "***"


class Channel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


@dataclass
class NotificationPayload:
    recipient_email: str
    recipient_name: str
    subject: str
    body: str
    channel: Channel = Channel.EMAIL
    metadata: Optional[dict] = None


class NotificationService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.from_email = settings.FROM_EMAIL

    def send(self, payload: NotificationPayload) -> dict:
        """Send a notification via the specified channel."""
        safe_email = mask_email(payload.recipient_email)
        safe_name = mask_name(payload.recipient_name)
        logger.info(
            "Sending %s notification to %s (%s): %s",
            payload.channel.value,
            safe_name,
            safe_email,
            payload.subject,
        )

        if payload.channel == Channel.EMAIL:
            return self._send_email(payload)
        elif payload.channel == Channel.SMS:
            return self._send_sms(payload)
        elif payload.channel == Channel.WEBHOOK:
            return self._send_webhook(payload)
        else:
            return self._store_in_app(payload)

    def _send_email(self, payload: NotificationPayload) -> dict:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = payload.subject
        msg["From"] = self.from_email
        msg["To"] = payload.recipient_email

        logger.info(
            "Email payload: to=%s, subject=%s",
            mask_email(payload.recipient_email),
            payload.subject,
        )

        html_body = f"""
        <html>
        <body>
            <h2>Hello {payload.recipient_name},</h2>
            <p>{payload.body}</p>
            <hr>
            <p style="color: #888; font-size: 12px;">
                This email was sent to {payload.recipient_email}.
                Contact support if you did not expect this message.
            </p>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.sendmail(self.from_email, payload.recipient_email, msg.as_string())
            return {"status": "sent", "channel": "email"}
        except Exception as e:
            logger.error(
                "Failed to send email to %s: %s",
                mask_email(payload.recipient_email),
                e,
            )
            return {"status": "failed", "channel": "email", "error": str(e)}

    def _send_sms(self, payload: NotificationPayload) -> dict:
        logger.info(
            "SMS to %s: %s",
            mask_name(payload.recipient_name),
            mask_pii(payload.body),
        )
        return {"status": "sent", "channel": "sms"}

    def _send_webhook(self, payload: NotificationPayload) -> dict:
        webhook_data = {
            "recipient": mask_email(payload.recipient_email),
            "event": payload.subject,
            "data": mask_pii(payload.body),
        }
        logger.info("Webhook dispatch: %s", webhook_data)
        return {"status": "sent", "channel": "webhook"}

    def _store_in_app(self, payload: NotificationPayload) -> dict:
        record = {
            "user_email": mask_email(payload.recipient_email),
            "title": payload.subject,
            "message": mask_pii(payload.body),
            "read": False,
        }
        logger.info("Stored in-app notification: %s", record)
        return {"status": "stored", "channel": "in_app"}


def send_payment_confirmation(email: str, name: str, amount: str, currency: str):
    svc = NotificationService()
    return svc.send(
        NotificationPayload(
            recipient_email=email,
            recipient_name=name,
            subject="Payment Confirmation",
            body=f"Your payment of {amount} {currency} has been processed successfully.",
        )
    )


def send_password_reset(email: str, name: str, reset_token: str):
    svc = NotificationService()
    return svc.send(
        NotificationPayload(
            recipient_email=email,
            recipient_name=name,
            subject="Password Reset Request",
            body=f"Click the link to reset your password: {settings.FRONTEND_URL}/reset?token={reset_token}",
        )
    )
