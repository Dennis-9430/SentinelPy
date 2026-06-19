"""Colectores de logs: reciben datos de distintas fuentes.

Cada collector implementa start()/stop() y envía los logs crudos
al parser correspondiente para su normalización.
"""


class SyslogCollector:
    """Colector de syslog: escucha mensajes UDP/TCP.

    Escucha en el puerto configurado (default: 5140) y recibe
    mensajes en formatos RFC 3164 (BSD) y RFC 5424 (ISO).
    """

    async def start(self):
        """Inicia la escucha de mensajes syslog.

        Crea un socket UDP y un socket TCP en el puerto configurado.
        Cada mensaje recibido se encola para parsing asíncrono.
        """
        raise NotImplementedError("Fase 2: implementar colector syslog")

    async def stop(self):
        """Detiene gracefulmente el colector.

        Cierra los sockets y espera a que los mensajes en cola
        terminen de procesarse.
        """
        raise NotImplementedError


class FileCollector:
    """Colector de archivos: monitorea archivos de log en tiempo real.

    Usa un mecanismo similar a tail -f para detectar nuevas líneas
    en archivos de log del sistema.
    """

    async def watch(self, path: str):
        """Vigila un archivo en busca de nuevas líneas.

        Argumentos:
            path: Ruta al archivo de log a monitorear.

        Cada línea nueva se envía al parser correspondiente
        según la extensión o configuración.
        """
        raise NotImplementedError("Fase 2: implementar file watcher")
