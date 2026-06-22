"""Tests para el colector syslog UDP.

Verifica que el colector reciba datagramas y los pase al pipeline.
"""

import asyncio
import pytest


class TestSyslogCollector:
    """Pruebas unitarias para el colector UDP syslog."""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Verifica que el colector inicie y se detenga sin errores."""
        # Crear pipeline mock
        pipeline_mock = PipelineMock()
        from app.services.collector import SyslogCollector

        colector = SyslogCollector(pipeline_mock)

        # Iniciar colector (usa un puerto de prueba)
        try:
            await colector.start()
            assert colector.transport is not None
            assert not colector.transport.is_closing()
        finally:
            await colector.stop()
            assert colector.transport.is_closing()

    @pytest.mark.asyncio
    async def test_recibir_datagrama(self):
        """Verifica que el colector reciba datos y los pase al pipeline.

        Envía un datagrama UDP al colector y verifica que el pipeline
        reciba el mensaje.
        """
        pipeline_mock = PipelineMock()
        from app.services.collector import SyslogCollector

        colector = SyslogCollector(pipeline_mock)

        try:
            await colector.start()

            # Enviar datagrama UDP al colector
            mensaje = b"<30>Oct  9 22:33:20 testhost testapp[123]: mensaje de prueba"
            from socket import AF_INET, SOCK_DGRAM, socket
            with socket(AF_INET, SOCK_DGRAM) as sock:
                sock.sendto(mensaje, ("127.0.0.1", colector.port))

            # Esperar a que el pipeline procese
            await asyncio.sleep(0.2)

            # Verificar que el pipeline recibió el mensaje
            assert len(pipeline_mock.recibidos) > 0
            assert mensaje.decode("utf-8").strip() in pipeline_mock.recibidos[0]
        finally:
            await colector.stop()


class PipelineMock:
    """Mock del pipeline para pruebas del colector."""

    def __init__(self):
        self.recibidos = []

    async def process(self, raw: str, origen: tuple | None = None):
        """Mock de process — solo registra lo recibido."""
        self.recibidos.append(raw)
        return {"event_type": "test", "severity": "info"}
