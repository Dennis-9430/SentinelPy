"""Colectores de logs: reciben datos de distintas fuentes.

Cada collector implementa start()/stop() y envía los logs crudos
al pipeline para su parsing y almacenamiento.
"""

import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class SyslogUDPHandler(asyncio.DatagramProtocol):
    """Manejador de datagramas UDP para syslog.

    asyncio.DatagramProtocol recibe paquetes UDP y los pasa al pipeline.
    Se crea una instancia por cada llamada a create_datagram_endpoint().
    """

    def __init__(self, pipeline):
        """
        Argumentos:
            pipeline: Instancia de Pipeline que procesa cada mensaje.
        """
        self.pipeline = pipeline

    def datagram_received(self, data: bytes, addr: tuple):
        """Callback de asyncio cuando llega un datagrama UDP.

        Decodifica el mensaje y lo envía al pipeline como tarea asíncrona
        para no bloquear el event loop con el procesamiento.

        Argumentos:
            data: Bytes del datagrama recibido.
            addr: Tupla (host, port) del remitente.
        """
        # Decodificar asumiendo UTF-8, con fallback a replace para caracteres raros
        raw = data.decode("utf-8", errors="replace").strip()

        if raw:
            logger.debug("UDP recibido de %s: %s", addr, raw[:100])
            # Crear tarea asíncrona para no bloquear el event loop
            asyncio.create_task(self.pipeline.process(raw, addr))


class SyslogCollector:
    """Colector de syslog: escucha mensajes UDP.

    Escucha en el puerto configurado (default: 5140) y recibe
    mensajes en formato RFC 3164 (BSD) principalmente.
    """

    def __init__(self, pipeline):
        """
        Argumentos:
            pipeline: Pipeline que procesa los mensajes recibidos.
        """
        self.host = settings.syslog_host
        self.port = settings.syslog_port
        self.pipeline = pipeline
        self.transport = None
        self._server = None

    async def start(self):
        """Inicia el servidor UDP para recibir mensajes syslog.

        Crea un endpoint UDP asíncrono en host:puerto.
        Cada datagrama recibido se maneja por SyslogUDPHandler.
        """
        loop = asyncio.get_running_loop()

        logger.info("Iniciando colector syslog UDP en %s:%s", self.host, self.port)

        try:
            # Crea el socket UDP y lo asocia al handler
            self.transport, _ = await loop.create_datagram_endpoint(
                lambda: SyslogUDPHandler(self.pipeline),
                local_addr=(self.host, self.port),
            )
            logger.info("Colector syslog UDP iniciado en puerto %s", self.port)
        except OSError as e:
            logger.error(
                "No se pudo iniciar colector syslog en puerto %s: %s", self.port, e
            )
            raise

    async def stop(self):
        """Detiene el colector syslog gracefulmente.

        Cierra el transporte UDP y espera a que terminen
        las tareas pendientes.
        """
        if self.transport:
            self.transport.close()
            logger.info("Colector syslog UDP detenido")


class FileCollector:
    """Colector de archivos: monitorea archivos de log en tiempo real.

    TODO: Implementar en fase posterior. Por ahora es placeholder.
    """

    async def watch(self, path: str):
        """Vigila un archivo en busca de nuevas líneas.

        Argumentos:
            path: Ruta al archivo de log a monitorear.

        Cada línea nueva se envía al parser correspondiente
        según la extensión o configuración.
        """
        raise NotImplementedError("Fase futura: implementar file watcher")
