"""Base abstracta para proveedores de Threat Intelligence.

Define IOCResult (resultado de consulta IOC) y BaseTIProvider (ABC)
que cada proveedor concreto debe implementar.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class IOCResult:
    """Resultado de una consulta a un proveedor de TI.

    Atributos:
        indicator: Valor del IOC consultado (IP, dominio, hash, URL).
        ioc_type: Tipo del IOC (ip | domain | hash | url).
        confidence: Nivel de confianza (0-100).
        provider: Nombre del proveedor que reportó el IOC.
        raw_response: Respuesta original del API (opcional).
    """

    indicator: str
    ioc_type: str
    confidence: int
    provider: str
    raw_response: dict | None = None


class BaseTIProvider(ABC):
    """Clase base abstracta para proveedores de Threat Intelligence.

    Cada proveedor concreto debe implementar:
      - name (property): nombre del proveedor.
      - supported_types (property): tipos de IOC soportados.
      - lookup_{tipo}(): método de consulta por tipo de IOC.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre del proveedor (ej: 'abuseipdb', 'virustotal')."""
        ...

    @property
    @abstractmethod
    def supported_types(self) -> list[str]:
        """Tipos de IOC soportados (ej: ['ip'], ['ip', 'domain'])."""
        ...

    async def lookup(self, indicator: str, ioc_type: str) -> IOCResult | None:
        """Consulta el IOC usando el método específico del tipo.

        Despacha a lookup_{ioc_type}. Si el tipo no es soportado
        o ocurre un error, retorna None.

        Argumentos:
            indicator: Valor del IOC a consultar.
            ioc_type: Tipo del IOC (ip, domain, hash, url).

        Retorna:
            IOCResult si la consulta fue exitosa, None en caso contrario.
        """
        if ioc_type not in self.supported_types:
            return None
        try:
            method = getattr(self, f"lookup_{ioc_type}")
            return await method(indicator)
        except Exception:
            return None
