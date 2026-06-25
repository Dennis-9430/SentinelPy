"""Notificador de alertas por email vía SMTP asíncrono."""

import logging
from email.message import EmailMessage
import aiosmtplib
from app.config import settings

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Envía alertas por email usando SMTP asíncrono.

    Usa aiosmtplib para no bloquear el event loop mientras envía.
    Configuración vía settings (smtp_host, smtp_port, etc.).
    """

    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.from_addr = settings.smtp_from
        self.to_addrs = settings.notify_to

    async def send(self, alerta: dict):
        """Envía la alerta por email si hay configuración SMTP."""
        if not self.user or not self.to_addrs:
            logger.debug("EmailNotifier: SMTP no configurado, skip")
            return

        severity = alerta.get("severity", "info").upper()
        title = alerta.get("title", "Alerta sin título")
        description = alerta.get("description", "")

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
            logger.info("Email enviado: %s → %s", title, self.to_addrs)
        except Exception as e:
            logger.error("Error al enviar email %s: %s", title, e)

    def _formatear_cuerpo(self, alerta: dict) -> str:
        """Formatea la alerta como texto plano."""
        severity = alerta.get("severity", "info").upper()
        title = alerta.get("title", "Sin título")
        description = alerta.get("description", "Sin descripción")

        lines = [
            f"[{severity}] {title}",
            "=" * 60,
            "",
            f"  Regla:      {alerta.get('rule_id', 'N/A')}",
            f"  Severidad:  {alerta.get('severity', 'N/A')}",
            f"  Eventos:    {alerta.get('event_count', 1)}",
            f"  ID Alerta:  {alerta.get('id', 'N/A')}",
            "",
            "  Descripción:",
            f"    {description}",
            "",
            "  — SentinelPy",
        ]
        return "\n".join(lines)
