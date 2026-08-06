"""Alert notifier via HTTP webhook (Slack, Discord, etc.)."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """Sends alerts to one or more HTTP webhooks.

    Supports Slack format (attachments) and Discord format (embeds).
    If the URL contains 'discord', uses the embed format.
    Otherwise, uses the Slack attachment format.
    """

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or settings.webhook_url
        self._client = httpx.AsyncClient(timeout=5.0)

    async def send(self, alerta: dict):
        """Send the alert to the configured webhook."""
        if not self.webhook_url:
            logger.debug("WebhookNotifier: URL not configured, skip")
            return

        severity = alerta.get("severity", "info")
        title = alerta.get("title", "Untitled alert")
        description = alerta.get("description", "")[:200]

        if "discord" in self.webhook_url.lower():
            payload = self._payload_discord(severity, title, description, alerta)
        else:
            payload = self._payload_slack(severity, title, description, alerta)

        try:
            resp = await self._client.post(self.webhook_url, json=payload)
            resp.raise_for_status()
            logger.info("Webhook sent: %s → %s", title, self.webhook_url)
        except Exception as e:
            logger.error("Error sending webhook %s: %s", title, e)

    def _payload_slack(
        self, severity: str, title: str, description: str, alerta: dict
    ) -> dict:
        """Slack format with attachments."""
        color_map = {
            "critical": "#dc2626",
            "high": "#ea580c",
            "medium": "#ca8a04",
            "low": "#2563eb",
            "info": "#6b7280",
        }
        return {
            "attachments": [
                {
                    "color": color_map.get(severity, "#6b7280"),
                    "title": f"🚨 [{severity.upper()}] {title}",
                    "text": description,
                    "fields": [
                        {
                            "title": "ID",
                            "value": alerta.get("id", "N/A")[:8],
                            "short": True,
                        },
                        {
                            "title": "Events",
                            "value": str(alerta.get("event_count", 1)),
                            "short": True,
                        },
                    ],
                    "footer": "SentinelPy",
                }
            ]
        }

    def _payload_discord(
        self, severity: str, title: str, description: str, alerta: dict
    ) -> dict:
        """Discord format with embeds."""
        color_map = {
            "critical": 0xDC2626,
            "high": 0xEA580C,
            "medium": 0xCA8A04,
            "low": 0x2563EB,
            "info": 0x6B7280,
        }
        return {
            "embeds": [
                {
                    "color": color_map.get(severity, 0x6B7280),
                    "title": f"[{severity.upper()}] {title}",
                    "description": description,
                    "fields": [
                        {
                            "name": "ID",
                            "value": alerta.get("id", "N/A")[:8],
                            "inline": True,
                        },
                        {
                            "name": "Events",
                            "value": str(alerta.get("event_count", 1)),
                            "inline": True,
                        },
                    ],
                    "footer": {"text": "SentinelPy"},
                }
            ]
        }
