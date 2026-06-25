"""Notificador de alertas vía webhook HTTP (Slack, Discord, etc.)."""

import json
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """Envía alertas a uno o más webhooks HTTP.

    Soporta formato Slack (attachments) y Discord (embeds).
    Si la URL contiene 'discord', usa formato embed.
    Caso contrario, usa formato Slack attachment.
    """

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or settings.webhook_url
        self._client = httpx.AsyncClient(timeout=5.0)

    async def send(self, alerta: dict):
        """Envía la alerta al webhook configurado."""
        if not self.webhook_url:
            logger.debug("WebhookNotifier: URL no configurada, skip")
            return

        severity = alerta.get("severity", "info")
        title = alerta.get("title", "Alerta sin título")
        description = alerta.get("description", "")[:200]

        if "discord" in self.webhook_url.lower():
            payload = self._payload_discord(severity, title, description, alerta)
        else:
            payload = self._payload_slack(severity, title, description, alerta)

        try:
            resp = await self._client.post(self.webhook_url, json=payload)
            resp.raise_for_status()
            logger.info("Webhook enviado: %s → %s", title, self.webhook_url)
        except Exception as e:
            logger.error("Error al enviar webhook %s: %s", title, e)

    def _payload_slack(self, severity: str, title: str, description: str, alerta: dict) -> dict:
        """Formato Slack con attachments."""
        color_map = {"critical": "#dc2626", "high": "#ea580c", "medium": "#ca8a04", "low": "#2563eb", "info": "#6b7280"}
        return {
            "attachments": [{
                "color": color_map.get(severity, "#6b7280"),
                "title": f"🚨 [{severity.upper()}] {title}",
                "text": description,
                "fields": [
                    {"title": "ID", "value": alerta.get("id", "N/A")[:8], "short": True},
                    {"title": "Eventos", "value": str(alerta.get("event_count", 1)), "short": True},
                ],
                "footer": "SentinelPy",
            }]
        }

    def _payload_discord(self, severity: str, title: str, description: str, alerta: dict) -> dict:
        """Formato Discord con embeds."""
        color_map = {"critical": 0xdc2626, "high": 0xea580c, "medium": 0xca8a04, "low": 0x2563eb, "info": 0x6b7280}
        return {
            "embeds": [{
                "color": color_map.get(severity, 0x6b7280),
                "title": f"[{severity.upper()}] {title}",
                "description": description,
                "fields": [
                    {"name": "ID", "value": alerta.get("id", "N/A")[:8], "inline": True},
                    {"name": "Eventos", "value": str(alerta.get("event_count", 1)), "inline": True},
                ],
                "footer": {"text": "SentinelPy"},
            }]
        }
