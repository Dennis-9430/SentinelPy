"""Abstract base for Threat Intelligence providers.

Defines IOCResult (IOC lookup result) and BaseTIProvider (ABC)
that every concrete provider must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class IOCResult:
    """Result of a query to a TI provider.

    Attributes:
        indicator: Value of the queried IOC (IP, domain, hash, URL).
        ioc_type: Type of the IOC (ip | domain | hash | url).
        confidence: Confidence level (0-100).
        provider: Name of the provider that reported the IOC.
        raw_response: Original API response (optional).
    """

    indicator: str
    ioc_type: str
    confidence: int
    provider: str
    raw_response: dict | None = None


class BaseTIProvider(ABC):
    """Abstract base class for Threat Intelligence providers.

    Every concrete provider must implement:
      - name (property): provider name.
      - supported_types (property): supported IOC types.
      - lookup_{type}(): lookup method per IOC type.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider (e.g. 'abuseipdb', 'virustotal')."""
        ...

    @property
    @abstractmethod
    def supported_types(self) -> list[str]:
        """Supported IOC types (e.g. ['ip'], ['ip', 'domain'])."""
        ...

    async def lookup(self, indicator: str, ioc_type: str) -> IOCResult | None:
        """Looks up the IOC using the type-specific method.

        Dispatches to lookup_{ioc_type}. If the type is not supported
        or an error occurs, returns None.

        Args:
            indicator: Value of the IOC to look up.
            ioc_type: Type of the IOC (ip, domain, hash, url).

        Returns:
            IOCResult if the lookup succeeded, None otherwise.
        """
        if ioc_type not in self.supported_types:
            return None
        try:
            method = getattr(self, f"lookup_{ioc_type}")
            return await method(indicator)
        except Exception:
            return None
