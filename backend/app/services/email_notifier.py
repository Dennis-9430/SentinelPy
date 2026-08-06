"""Email alert notifier via async SMTP."""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Sends alerts by email using async SMTP.

    Uses aiosmtplib to avoid blocking the event loop while sending.
    Configured via settings (smtp_host, smtp_port, etc.).
    """

    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.from_addr = settings.smtp_from
        self.to_addrs = settings.notify_to

    async def send(self, alerta: dict):
        """Send the alert by email if SMTP configuration exists."""
        if not self.user or not self.to_addrs:
            logger.debug("EmailNotifier: SMTP not configured, skip")
            return

        severity = alerta.get("severity", "info").upper()
        title = alerta.get("title", "Untitled alert")
        alerta.get("description", "")

        msg = EmailMessage()
        msg["From"] = self.from_addr or self.user
        msg["To"] = ", ".join(self.to_addrs)
        msg["Subject"] = f"[{severity}] SentinelPy — {title}"

        body = self._formatear_cuerpo(alerta)
        msg.set_content(body)

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                start_tls=True,
                timeout=10.0,
            )
            logger.info("Email sent: %s → %s", title, self.to_addrs)
        except Exception as e:
            logger.error("Error sending email %s: %s", title, e)

    def _formatear_cuerpo(self, alerta: dict) -> str:
        """Format the alert as plain text."""
        severity = alerta.get("severity", "info").upper()
        title = alerta.get("title", "Untitled")
        description = alerta.get("description", "No description")

        lines = [
            f"[{severity}] {title}",
            "=" * 60,
            "",
            f"  Rule:       {alerta.get('rule_id', 'N/A')}",
            f"  Severity:   {alerta.get('severity', 'N/A')}",
            f"  Events:     {alerta.get('event_count', 1)}",
            f"  Alert ID:   {alerta.get('id', 'N/A')}",
            "",
            "  Description:",
            f"    {description}",
            "",
            "  — SentinelPy",
        ]
        return "\n".join(lines)
