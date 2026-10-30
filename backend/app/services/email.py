"""Outbound email. Uses SMTP when configured; otherwise the message is not sent.

When SMTP is not configured the delivery attempt is reported as `not_configured`
so callers (and the admin health page) can surface it honestly.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def email_configured() -> bool:
    return bool(get_settings().smtp_host)


def _send_sync(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    assert settings.smtp_host
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> str:
    """Send an email. Returns 'sent', 'not_configured' or 'failed'."""
    if not email_configured():
        logger.info("Email not sent (SMTP not configured): subject=%s", subject)
        return "not_configured"
    try:
        await asyncio.to_thread(_send_sync, to, subject, body)
        return "sent"
    except Exception:
        logger.exception("Email delivery failed: subject=%s", subject)
        return "failed"
