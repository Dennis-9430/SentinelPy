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
