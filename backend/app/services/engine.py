"""Motor de correlación: evalúa eventos contra reglas de detección.

El corazón de SentinelPy. Cada evento que ingresa se evalúa contra
todas las reglas activas. Si una regla matchea, se genera una alerta.

Soporta correlación temporal: si una regla tiene correlation_window,
acumula eventos en una ventana de tiempo y solo genera/actualiza
la alerta dentro de esa ventana.
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.rule import DetectionRule

logger = logging.getLogger(__name__)


class CorrelationEngine:
    """Motor de correlación de eventos.

    Mantiene un caché de reglas activas en memoria y evalúa
    cada evento entrante contra todas ellas.

    Flujo:
        1. Se cargan las reglas activas desde la BD al iniciar
        2. Por cada evento que llega, se evalúa contra todas las reglas
        3. Si una regla matchea:
           a. Sin correlation_window → alerta inmediata
           b. Con correlation_window → acumula en ventana temporal
        4. Las alertas se crean/actualizan vía callbacks
    """

    def __init__(self):
        """Inicializa el motor sin reglas. Llamar a cargar_reglas() antes de usar."""
        self._reglas: list[DetectionRule] = []
        self._callbacks: list = []
        self._callbacks_actualizar: list = []
        # Ventanas temporales: rule_id -> {event_count, first_event_at, last_event_at, expires_at}
        self._ventanas: dict[str, dict] = {}

    def registrar_callback(self, callback):
        """Registra una función que se ejecuta cuando se crea una alerta.

        Cada callback recibe un dict con los datos de la alerta y debe
        retornar la alerta creada. Se pueden registrar múltiples callbacks.

        Argumentos:
            callback: Función asíncrona que recibe (datos_alerta) y retorna la alerta.
        """
        self._callbacks.append(callback)

    def registrar_callback_actualizar(self, callback):
        """Registra un callback para actualizar alertas dentro de ventanas.

        Se ejecuta cuando un evento matchea una regla con correlation_window
        y ya existe una ventana activa. Recibe un dict con rule_id,
        event_count, last_event_at.

        Argumentos:
            callback: Función asíncrona que recibe (datos_actualizacion).
        """
        self._callbacks_actualizar.append(callback)

    def cargar_reglas(self, reglas: list[DetectionRule | dict]):
        """Carga o recarga las reglas activas en memoria.

        Se llama al iniciar la app y cada vez que se crea/actualiza/elimina
        una regla para mantener el caché sincronizado.

        Filtra automáticamente solo las reglas con status='active'.
        Soporta tanto objetos DetectionRule como dicts.

        Al recargar, las ventanas activas se limpian para evitar
        inconsistencias con reglas modificadas.

        Argumentos:
            reglas: Lista de DetectionRule o dict con status='active'.
        """

        def _status(regla):
            if isinstance(regla, dict):
                return regla.get("status", "")
            return getattr(regla, "status", "")

        self._reglas = [r for r in reglas if _status(r) == "active"]
        # Limpiar ventanas al recargar reglas
        self._ventanas.clear()
        logger.info(
            "Motor de correlación: %d reglas activas cargadas (de %d recibidas)",
            len(self._reglas),
            len(reglas),
        )

    async def evaluate(self, evento: dict) -> list[dict]:
        """Evalúa un evento contra todas las reglas activas.

        Por cada regla que matchea, se crea una alerta o se actualiza
        una existente si la regla tiene correlación temporal.

        Argumentos:
            evento: Dict con los datos del evento normalizado (ya guardado en DB).

        Retorna:
            Lista de alertas generadas (dicts).
        """
        alertas_generadas = []

        for regla in self._reglas:
            if self._evaluar_regla(regla, evento):
                logger.info(
                    "Regla '%s' matcheó evento %s",
                    self._campo_regla(regla, "title"),
                    evento.get("id", "unknown"),
                )

                alerta = await self._manejar_match(regla, evento)
                if alerta:
                    alertas_generadas.append(alerta)

        return alertas_generadas

    async def _manejar_match(
        self, regla: DetectionRule | dict, evento: dict
    ) -> dict | None:
        """Maneja un match de regla, considerando correlación temporal.

        Si la regla tiene correlation_window:
          - Si hay ventana activa → actualiza contadores
          - Si no hay ventana o expiró → crea nueva alerta
        Si no tiene correlation_window → alerta inmediata.

        Argumentos:
            regla: Regla que matcheó.
            evento: Evento que activó la regla.

        Retorna:
            Dict de alerta creada, o None si solo se actualizó.
        """
        correlation_window = self._campo_regla(regla, "correlation_window")
        rule_id_raw = self._campo_regla(regla, "id")
        rule_id = str(rule_id_raw) if rule_id_raw else None

        # Sin correlación temporal → alerta inmediata (comportamiento actual)
        if not correlation_window or not rule_id:
            return await self._crear_alerta(regla, evento)

        ahora = datetime.now(UTC)
        ventana = self._ventanas.get(rule_id)
        ts_evento = evento.get("event_timestamp", ahora)

        if ventana and ventana["expires_at"] > ahora:
            # ── Dentro de la ventana → actualizar contadores ──────────
            ventana["event_count"] += 1
            ventana["last_event_at"] = ts_evento
            self._ventanas[rule_id] = ventana

            logger.info(
                "Ventana temporal activa para regla %s: %d eventos",
                rule_id,
                ventana["event_count"],
            )

            # Ejecutar callbacks de actualización
            datos_actualizacion = {
                "rule_id": rule_id,
                "event_count": ventana["event_count"],
                "last_event_at": ventana["last_event_at"],
            }
            await self._ejecutar_callbacks_actualizar(datos_actualizacion)
            return None  # No se creó nueva alerta

        # ── Nueva ventana o ventana expirada → crear alerta ──────────
        expiracion = ahora + timedelta(seconds=correlation_window)
        self._ventanas[rule_id] = {
            "event_count": 1,
            "first_event_at": ts_evento,
            "last_event_at": ts_evento,
            "expires_at": expiracion,
        }

        return await self._crear_alerta(regla, evento)

    @staticmethod
    def _campo_regla(regla: Any, campo: str):
        """Obtiene un campo de una regla, soportando dict y objeto.

        Permite que el motor reciba tanto objetos DetectionRule
        (desde la app) como dicts (desde tests o fixtures).
        """
        return (
            regla.get(campo) if isinstance(regla, dict) else getattr(regla, campo, None)
        )

    def _evaluar_regla(self, regla: DetectionRule | dict, evento: dict) -> bool:
        """Evalúa si un evento cumple las condiciones de una regla.

        Argumentos:
            regla: DetectionRule (o dict) a evaluar.
            evento: Dict con datos del evento.

        Retorna:
            True si el evento matchea todas las condiciones.
        """
        condiciones = self._campo_regla(regla, "conditions")

        # Si el operador raíz es and/or, evaluar como grupo
        if isinstance(condiciones, dict) and "operator" in condiciones:
            operador = str(condiciones.get("operator")).lower()
            if operador in ("and", "or"):
                return self._evaluar_grupo(condiciones, evento)
            else:
                # Condición simple
                return self._evaluar_condicion(condiciones, evento)

        # Si es una lista, todas deben cumplirse (AND implícito)
        if isinstance(condiciones, list):
            return all(self._evaluar_condicion(c, evento) for c in condiciones)

        # Condición simple como dict
        return self._evaluar_condicion(condiciones, evento)

    def _evaluar_grupo(self, grupo: dict, evento: dict) -> bool:
        """Evalúa un grupo de condiciones (AND/OR).

        Argumentos:
            grupo: Dict con "operator" y "conditions".
            evento: Dict con datos del evento.

        Retorna:
            Resultado de la evaluación lógica.
        """
        operador = str(grupo.get("operator", "and")).lower()
        condiciones = grupo.get("conditions", [])

        if operador == "and":
            return all(
                self._evaluar_regla({"conditions": c}, evento) for c in condiciones
            )
        elif operador == "or":
            return any(
                self._evaluar_regla({"conditions": c}, evento) for c in condiciones
            )
        elif operador == "not":
            if condiciones:
                return not self._evaluar_regla({"conditions": condiciones[0]}, evento)
            return True

        return False

    def _evaluar_condicion(self, condicion: dict, evento: dict) -> bool:
        """Evalúa una condición individual contra un evento.

        Argumentos:
            condicion: Dict con "field", "operator", "value".
            evento: Dict con datos del evento.

        Retorna:
            True si la condición se cumple.

        Operadores soportados:
            - eq: igualdad (case-insensitive para strings)
            - neq: no igual
            - contains: el campo contiene el valor (string)
            - gt, gte, lt, lte: comparaciones numéricas
            - in: el valor está en una lista
            - regex: el campo matchea una expresión regular
            - exists: el campo existe y no es None
            - not_exists: el campo es None o no existe
            - startswith: el campo empieza con el valor
            - endswith: el campo termina con el valor
        """
        field = condicion.get("field")
        operator = condicion.get("operator", "eq")
        value = condicion.get("value")

        # Obtener el valor del campo en el evento
        valor_evento = evento.get(field) if field else None

        # Manejar field anidado con notación punto (ej: "source_ip")
        if field and "." in field:
            partes = field.split(".")
            valor_evento = evento
            for parte in partes:
                if isinstance(valor_evento, dict):
                    valor_evento = valor_evento.get(parte)
                else:
                    valor_evento = None
                    break

        # Evaluar según el operador
        try:
            if operator == "eq":
                return self._eq(valor_evento, value)
            elif operator in ("neq", "not"):
                return not self._eq(valor_evento, value)
            elif operator == "contains":
                return self._contains(valor_evento, value)
            elif operator == "gt":
                return self._compare(valor_evento, value, lambda a, b: a > b)
            elif operator == "gte":
                return self._compare(valor_evento, value, lambda a, b: a >= b)
            elif operator == "lt":
                return self._compare(valor_evento, value, lambda a, b: a < b)
            elif operator == "lte":
                return self._compare(valor_evento, value, lambda a, b: a <= b)
            elif operator == "in":
                return self._in_list(valor_evento, value)
            elif operator == "regex":
                return self._regex(valor_evento, value)
            elif operator == "exists":
                return valor_evento is not None
            elif operator == "not_exists":
                return valor_evento is None
            elif operator == "startswith":
                return self._startswith(valor_evento, value)
            elif operator == "endswith":
                return self._endswith(valor_evento, value)
            else:
                logger.warning("Operador desconocido: %s", operator)
                return False
        except (TypeError, ValueError, re.error) as e:
            logger.debug("Error evaluando condición %s: %s", condicion, e)
            return False

    def _eq(self, valor_evento: Any, value: Any) -> bool:
        """Comparación de igualdad case-insensitive para strings."""
        if valor_evento is None:
            return False
        if isinstance(valor_evento, str) and isinstance(value, str):
            return valor_evento.lower() == value.lower()
        return valor_evento == value

    def _contains(self, valor_evento: Any, value: Any) -> bool:
        """Verifica si el campo contiene el valor (case-insensitive)."""
        if valor_evento is None or value is None:
            return False
        return str(value).lower() in str(valor_evento).lower()

    def _compare(self, valor_evento: Any, value: Any, op) -> bool:
        """Comparación numérica."""
        if valor_evento is None or value is None:
            return False
        return op(float(valor_evento), float(value))

    def _in_list(self, valor_evento: Any, value: Any) -> bool:
        """Verifica si el valor del evento está en la lista de valores.

        Si value es un string, lo trata como lista de un elemento.
        """
        if valor_evento is None:
            return False
        if not isinstance(value, list):
            value = [value]
        valor_str = str(valor_evento).lower()
        return any(str(v).lower() == valor_str for v in value)

    def _regex(self, valor_evento: Any, pattern: str) -> bool:
        """Verifica si el campo matchea una expresión regular."""
        if valor_evento is None or pattern is None:
            return False
        return bool(re.search(pattern, str(valor_evento)))

    def _startswith(self, valor_evento: Any, value: Any) -> bool:
        """Verifica si el campo empieza con el valor."""
        if valor_evento is None or value is None:
            return False
        return str(valor_evento).lower().startswith(str(value).lower())

    def _endswith(self, valor_evento: Any, value: Any) -> bool:
        """Verifica si el campo termina con el valor."""
        if valor_evento is None or value is None:
            return False
        return str(valor_evento).lower().endswith(str(value).lower())

    async def _crear_alerta(
        self, regla: DetectionRule | dict, evento: dict
    ) -> dict | None:
        """Crea una alerta usando los callbacks registrados.

        Argumentos:
            regla: La regla que matcheó (objeto o dict).
            evento: El evento que activó la regla.

        Retorna:
            Dict con los datos de la alerta generada.
        """
        datos_alerta = {
            "rule_id": self._campo_regla(regla, "id"),
            "title": self._campo_regla(regla, "alert_title"),
            "severity": self._campo_regla(regla, "alert_severity"),
            "description": (
                f"Regla '{self._campo_regla(regla, 'title')}' activada por evento "
                f"{evento.get('event_type', 'unknown')} desde {evento.get('source', 'unknown')}: "
                f"{evento.get('description', 'sin descripción')[:200]}"
            ),
            "status": "open",
            "event_count": 1,
            "first_event_at": evento.get("event_timestamp", datetime.now(UTC)),
            "last_event_at": evento.get("event_timestamp", datetime.now(UTC)),
        }

        # Ejecutar todos los callbacks registrados
        if not self._callbacks:
            logger.debug("No hay callbacks registrados — alerta generada en memoria")
            return datos_alerta

        for callback in self._callbacks:
            try:
                await callback(datos_alerta)
            except Exception as e:
                logger.error("Error en callback: %s", e, exc_info=True)

        return datos_alerta

    async def _ejecutar_callbacks_actualizar(self, datos: dict):
        """Ejecuta todos los callbacks de actualización registrados.

        Argumentos:
            datos: Dict con rule_id, event_count, last_event_at.
        """
        for callback in self._callbacks_actualizar:
            try:
                await callback(datos)
            except Exception as e:
                logger.error("Error en callback de actualización: %s", e, exc_info=True)

    @property
    def reglas_activas(self) -> int:
        """Cantidad de reglas activas cargadas en memoria."""
        return len(self._reglas)

    @property
    def ventanas_activas(self) -> int:
        """Cantidad de ventanas temporales activas."""
        ahora = datetime.now(UTC)
        return sum(1 for v in self._ventanas.values() if v["expires_at"] > ahora)
