"""Tests para el sistema de notificaciones."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notifier import ConsoleNotifier, MultiNotifier


@pytest.mark.asyncio
async def test_console_notifier_logs_alerta():
    """ConsoleNotifier debe loguear la alerta sin errores."""
    notifier = ConsoleNotifier()
    alerta = {
        "id": "123",
        "title": "Alerta de prueba",
        "severity": "high",
        "description": "Descripción de prueba",
    }
    # No debe lanzar excepción
    await notifier.send(alerta)


@pytest.mark.asyncio
async def test_multi_notifier_ejecuta_todos():
    """MultiNotifier debe ejecutar todos los notificadores registrados."""
    mock1 = AsyncMock()
    mock2 = AsyncMock()

    multi = MultiNotifier()
    multi.agregar(mock1)
    multi.agregar(mock2)

    alerta = {"id": "1", "severity": "high", "title": "Test"}
    await multi.send_all(alerta)

    mock1.send.assert_awaited_once_with(alerta)
    mock2.send.assert_awaited_once_with(alerta)


@pytest.mark.asyncio
async def test_multi_notifier_filtra_severidad():
    """MultiNotifier debe respetar el min_severity de cada notificador."""
    mock = AsyncMock()

    multi = MultiNotifier()
    multi.agregar(mock, min_severity="critical")

    # Alerta de severidad "high" no debe enviarse si el mínimo es "critical"
    alerta = {"id": "1", "severity": "high", "title": "Test"}
    await multi.send_all(alerta)
    mock.send.assert_not_awaited()

    # Alerta de severidad "critical" sí debe enviarse
    alerta2 = {"id": "2", "severity": "critical", "title": "Test2"}
    await multi.send_all(alerta2)
    mock.send.assert_awaited_once_with(alerta2)


@pytest.mark.asyncio
async def test_multi_notifier_error_no_detiene():
    """Un notificador que falla no debe impedir que los otros sigan."""
    mock_exitoso = AsyncMock()
    mock_fallido = MagicMock()

    # Hacer que el método send del mock_fallido lance excepción
    async def fallar(_):
        raise RuntimeError("Fallo simulado")

    mock_fallido.send = fallar

    multi = MultiNotifier()
    multi.agregar(mock_fallido)
    multi.agregar(mock_exitoso)

    alerta = {"id": "1", "severity": "high", "title": "Test"}
    await multi.send_all(alerta)

    mock_exitoso.send.assert_awaited_once_with(alerta)


@pytest.mark.asyncio
async def test_email_notifier_skips_sin_config():
    """EmailNotifier debe hacer skip si no hay configuración SMTP."""
    from app.services import email_notifier as en_mod

    with patch.object(en_mod, "settings") as mock_settings:
        mock_settings.smtp_user = ""
        mock_settings.smtp_host = ""
        mock_settings.smtp_port = 587
        mock_settings.smtp_password = ""
        mock_settings.smtp_from = ""
        mock_settings.notify_to = []

        notifier = en_mod.EmailNotifier()
        alerta = {"id": "1", "severity": "high", "title": "Test"}
        # No debe lanzar excepción ni intentar enviar
        await notifier.send(alerta)


@pytest.mark.asyncio
async def test_webhook_notifier_skips_sin_url():
    """WebhookNotifier debe hacer skip si no hay URL configurada."""
    WebhookNotifier = __import__(
        "app.services.webhook_notifier", fromlist=["WebhookNotifier"]
    ).WebhookNotifier
    notifier = WebhookNotifier(webhook_url="")
    alerta = {"id": "1", "severity": "high", "title": "Test"}
    await notifier.send(alerta)


@pytest.mark.asyncio
async def test_console_severity_filtering():
    """ConsoleNotifier debe manejar cualquier severidad sin errores."""
    notifier = ConsoleNotifier()

    for severity in ["critical", "high", "medium", "low", "info"]:
        alerta = {"id": "1", "severity": severity, "title": f"Test {severity}"}
        await notifier.send(alerta)  # No debe explotar


# ── EmailNotifier ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_email_notifier_send_exitoso():
    """EmailNotifier debe enviar email con los parámetros correctos."""
    from app.services import email_notifier as en_mod

    with (
        patch.object(en_mod, "settings") as mock_settings,
        patch("app.services.email_notifier.aiosmtplib.send") as mock_send,
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = "user@example.com"
        mock_settings.smtp_password = "secret"
        mock_settings.smtp_from = "sentinel@example.com"
        mock_settings.notify_to = ["admin@example.com", "ops@example.com"]

        notifier = en_mod.EmailNotifier()
        alerta = {
            "id": "alert-001",
            "title": "Alerta de prueba",
            "severity": "high",
            "description": "Descripción de prueba",
            "rule_id": "RULE-001",
            "event_count": 5,
        }
        await notifier.send(alerta)

        mock_send.assert_awaited_once()
        args, kwargs = mock_send.call_args
        msg = args[0]

        # Verificar headers del email
        assert msg["From"] == "sentinel@example.com"
        assert msg["To"] == "admin@example.com, ops@example.com"
        assert msg["Subject"] == "[HIGH] SentinelPy — Alerta de prueba"

        # Verificar cuerpo del email
        body = msg.get_content()
        assert "[HIGH] Alerta de prueba" in body
        assert "RULE-001" in body
        assert "high" in body
        assert "5" in body
        assert "alert-001" in body
        assert "Descripción de prueba" in body

        # Verificar parámetros SMTP
        assert kwargs["hostname"] == "smtp.example.com"
        assert kwargs["port"] == 587
        assert kwargs["username"] == "user@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["start_tls"] is True
        assert kwargs["timeout"] == 10.0


@pytest.mark.asyncio
async def test_email_notifier_error_manejado():
    """EmailNotifier debe manejar errores de envío sin propagar excepciones."""
    from app.services import email_notifier as en_mod

    with (
        patch.object(en_mod, "settings") as mock_settings,
        patch("app.services.email_notifier.aiosmtplib.send") as mock_send,
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_user = "user@example.com"
        mock_settings.smtp_password = "secret"
        mock_settings.smtp_from = "sentinel@example.com"
        mock_settings.notify_to = ["admin@example.com"]

        mock_send.side_effect = Exception("Connection refused")

        notifier = en_mod.EmailNotifier()
        alerta = {"id": "1", "severity": "high", "title": "Test"}
        # No debe lanzar excepción
        await notifier.send(alerta)
        mock_send.assert_awaited_once()


def test_email_notifier_formateo_cuerpo():
    """_formatear_cuerpo debe incluir todos los campos de la alerta."""
    from app.services import email_notifier as en_mod

    with patch.object(en_mod, "settings"):
        notifier = en_mod.EmailNotifier()
        alerta = {
            "id": "ALERT-999",
            "title": "Incidente de seguridad",
            "severity": "critical",
            "description": "Se detectó un evento crítico en el sistema",
            "rule_id": "R-42",
            "event_count": 10,
        }
        body = notifier._formatear_cuerpo(alerta)

        assert "[CRITICAL] Incidente de seguridad" in body
        assert "R-42" in body
        assert "critical" in body
        assert "10" in body
        assert "ALERT-999" in body
        assert "Se detectó un evento crítico en el sistema" in body
        assert "=" * 60 in body


# ── WebhookNotifier ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_notifier_send_slack():
    """WebhookNotifier debe enviar payload con formato Slack."""
    from app.services.webhook_notifier import WebhookNotifier

    notifier = WebhookNotifier(webhook_url="https://hooks.example.com/webhook")
    mock_post = AsyncMock()
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    with patch.object(notifier._client, "post", mock_post):
        alerta = {
            "id": "alert-001",
            "title": "Alerta de prueba",
            "severity": "medium",
            "description": "Descripción del evento",
            "event_count": 3,
        }
        await notifier.send(alerta)

        mock_post.assert_awaited_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://hooks.example.com/webhook"

        payload = kwargs["json"]
        assert "attachments" in payload
        attachment = payload["attachments"][0]
        assert attachment["color"] == "#ca8a04"  # medium
        assert attachment["title"] == "🚨 [MEDIUM] Alerta de prueba"
        assert attachment["text"] == "Descripción del evento"
        assert attachment["footer"] == "SentinelPy"

        fields = attachment["fields"]
        assert fields[0]["title"] == "ID"
        assert fields[0]["value"] == "alert-00"  # [:8]
        assert fields[0]["short"] is True
        assert fields[1]["title"] == "Eventos"
        assert fields[1]["value"] == "3"
        assert fields[1]["short"] is True


@pytest.mark.asyncio
async def test_webhook_notifier_send_discord():
    """WebhookNotifier debe enviar payload con formato Discord."""
    from app.services.webhook_notifier import WebhookNotifier

    notifier = WebhookNotifier(webhook_url="https://discord.com/api/webhooks/123/token")
    mock_post = AsyncMock()
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    with patch.object(notifier._client, "post", mock_post):
        alerta = {
            "id": "disc-alert",
            "title": "Alerta Discord",
            "severity": "critical",
            "description": "Algo grave pasó",
            "event_count": 7,
        }
        await notifier.send(alerta)

        mock_post.assert_awaited_once()
        args, kwargs = mock_post.call_args
        assert "discord" in args[0]

        payload = kwargs["json"]
        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert embed["color"] == 0xDC2626  # critical
        assert embed["title"] == "[CRITICAL] Alerta Discord"
        assert embed["description"] == "Algo grave pasó"
        assert embed["footer"]["text"] == "SentinelPy"

        fields = embed["fields"]
        assert fields[0]["name"] == "ID"
        assert fields[0]["value"] == "disc-ale"  # [:8]
        assert fields[0]["inline"] is True
        assert fields[1]["name"] == "Eventos"
        assert fields[1]["value"] == "7"
        assert fields[1]["inline"] is True


@pytest.mark.asyncio
async def test_webhook_notifier_error_manejado():
    """WebhookNotifier debe manejar errores HTTP sin propagar excepciones."""
    from app.services.webhook_notifier import WebhookNotifier

    notifier = WebhookNotifier(webhook_url="https://hooks.example.com/webhook")
    mock_post = AsyncMock()
    mock_post.return_value = MagicMock(status_code=500)
    mock_post.return_value.raise_for_status = MagicMock(
        side_effect=Exception("Server Error")
    )

    with patch.object(notifier._client, "post", mock_post):
        alerta = {"id": "1", "severity": "high", "title": "Test"}
        # No debe lanzar excepción
        await notifier.send(alerta)
        mock_post.assert_awaited_once()


def test_webhook_notifier_payload_slack():
    """_payload_slack debe generar estructura correcta con color map."""
    from app.services.webhook_notifier import WebhookNotifier

    notifier = WebhookNotifier(webhook_url="https://hooks.example.com/webhook")
    alerta = {"id": "test-001", "event_count": 5}
    color_expected = {
        "critical": "#dc2626",
        "high": "#ea580c",
        "medium": "#ca8a04",
        "low": "#2563eb",
        "info": "#6b7280",
        "unknown": "#6b7280",  # default
    }

    for severity, expected_color in color_expected.items():
        payload = notifier._payload_slack(severity, f"Test {severity}", "desc", alerta)
        attachment = payload["attachments"][0]
        assert attachment["color"] == expected_color
        assert attachment["title"] == f"🚨 [{severity.upper()}] Test {severity}"

        fields = attachment["fields"]
        assert fields[0]["title"] == "ID"
        assert fields[0]["value"] == "test-001"
        assert fields[0]["short"] is True
        assert fields[1]["title"] == "Eventos"
        assert fields[1]["value"] == "5"
        assert fields[1]["short"] is True


def test_webhook_notifier_payload_discord():
    """_payload_discord debe generar embed correcto con color map."""
    from app.services.webhook_notifier import WebhookNotifier

    notifier = WebhookNotifier(webhook_url="https://discord.com/api/webhooks/123")
    alerta = {"id": "disc-001", "event_count": 3}
    color_expected = {
        "critical": 0xDC2626,
        "high": 0xEA580C,
        "medium": 0xCA8A04,
        "low": 0x2563EB,
        "info": 0x6B7280,
        "unknown": 0x6B7280,  # default
    }

    for severity, expected_color in color_expected.items():
        payload = notifier._payload_discord(
            severity, f"Disc {severity}", "desc", alerta
        )
        embed = payload["embeds"][0]
        assert embed["color"] == expected_color
        assert embed["title"] == f"[{severity.upper()}] Disc {severity}"
        assert embed["description"] == "desc"
        assert embed["footer"]["text"] == "SentinelPy"

        fields = embed["fields"]
        assert fields[0]["name"] == "ID"
        assert fields[0]["value"] == "disc-001"
        assert fields[0]["inline"] is True
        assert fields[1]["name"] == "Eventos"
        assert fields[1]["value"] == "3"
        assert fields[1]["inline"] is True
