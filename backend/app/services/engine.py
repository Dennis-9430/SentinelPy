"""Correlation engine: evaluates events against detection rules.

The heart of SentinelPy. Every incoming event is evaluated against
all active rules. If a rule matches, an alert is generated.

Supports temporal correlation: if a rule has a correlation_window,
events are accumulated in a time window and the alert is only
generated/updated within that window.
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.rule import DetectionRule

logger = logging.getLogger(__name__)


class CorrelationEngine:
    """Event correlation engine.

    Keeps an in-memory cache of active rules and evaluates
    every incoming event against all of them.

    Flow:
        1. Active rules are loaded from the DB at startup
        2. Each incoming event is evaluated against all rules
        3. If a rule matches:
           a. Without correlation_window → immediate alert
           b. With correlation_window → accumulates in a time window
        4. Alerts are created/updated via callbacks
    """

    def __init__(self):
        """Initializes the engine without rules. Call cargar_reglas() before using."""
        self._reglas: list[DetectionRule] = []
        self._callbacks: list = []
        self._callbacks_actualizar: list = []
        # Time windows: rule_id -> {event_count, first_event_at, last_event_at, expires_at}
        self._ventanas: dict[str, dict] = {}

    def registrar_callback(self, callback):
        """Registers a function that runs when an alert is created.

        Each callback receives a dict with the alert data and must
        return the created alert. Multiple callbacks can be registered.

        Args:
            callback: Async function that receives (datos_alerta) and returns the alert.
        """
        self._callbacks.append(callback)

    def registrar_callback_actualizar(self, callback):
        """Registers a callback for updating alerts within windows.

        It runs when an event matches a rule with a correlation_window
        and an active window already exists. It receives a dict with rule_id,
        event_count, last_event_at.

        Args:
            callback: Async function that receives (datos_actualizacion).
        """
        self._callbacks_actualizar.append(callback)

    def cargar_reglas(self, reglas: list[DetectionRule | dict]):
        """Loads or reloads the active rules into memory.

        Called at app startup and every time a rule is created/updated/deleted
        to keep the cache in sync.

        Automatically filters only the rules with status='active'.
        Supports both DetectionRule objects and dicts.

        On reload, active windows are cleared to avoid
        inconsistencies with modified rules.

        Args:
            reglas: List of DetectionRule or dict with status='active'.
        """

        def _status(regla):
            if isinstance(regla, dict):
                return regla.get("status", "")
            return getattr(regla, "status", "")

        self._reglas = [r for r in reglas if _status(r) == "active"]
        # Clear windows when rules are reloaded
        self._ventanas.clear()
        logger.info(
            "Correlation engine: %d active rules loaded (of %d received)",
            len(self._reglas),
            len(reglas),
        )

    async def evaluate(self, evento: dict) -> list[dict]:
        """Evaluates an event against all active rules.

        For each rule that matches, an alert is created or an existing
        one is updated if the rule has temporal correlation.

        Args:
            evento: Dict with the normalized event data (already saved in the DB).

        Returns:
            List of generated alerts (dicts).
        """
        alertas_generadas = []

        for regla in self._reglas:
            if self._evaluar_regla(regla, evento):
                logger.info(
                    "Rule '%s' matched event %s",
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
        """Handles a rule match, considering temporal correlation.

        If the rule has a correlation_window:
          - If there is an active window → updates counters
          - If there is no window or it expired → creates a new alert
        If it has no correlation_window → immediate alert.

        Args:
            regla: The rule that matched.
            evento: The event that triggered the rule.

        Returns:
            Dict of the created alert, or None if it was only updated.
        """
        correlation_window = self._campo_regla(regla, "correlation_window")
        rule_id_raw = self._campo_regla(regla, "id")
        rule_id = str(rule_id_raw) if rule_id_raw else None

        # No temporal correlation → immediate alert (current behavior)
        if not correlation_window or not rule_id:
            return await self._crear_alerta(regla, evento)

        ahora = datetime.now(UTC)
        ventana = self._ventanas.get(rule_id)
        ts_evento = evento.get("event_timestamp", ahora)

        if ventana and ventana["expires_at"] > ahora:
            # ── Within the window → update counters ────────────────────
            ventana["event_count"] += 1
            ventana["last_event_at"] = ts_evento
            self._ventanas[rule_id] = ventana

            logger.info(
                "Active time window for rule %s: %d events",
                rule_id,
                ventana["event_count"],
            )

            # Run update callbacks
            datos_actualizacion = {
                "rule_id": rule_id,
                "event_count": ventana["event_count"],
                "last_event_at": ventana["last_event_at"],
            }
            await self._ejecutar_callbacks_actualizar(datos_actualizacion)
            return None  # No new alert was created

        # ── New window or expired window → create alert ────────────────
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
        """Gets a field from a rule, supporting dict and object.

        Allows the engine to receive both DetectionRule objects
        (from the app) and dicts (from tests or fixtures).
        """
        return (
            regla.get(campo) if isinstance(regla, dict) else getattr(regla, campo, None)
        )

    def _evaluar_regla(self, regla: DetectionRule | dict, evento: dict) -> bool:
        """Evaluates whether an event meets a rule's conditions.

        Args:
            regla: DetectionRule (or dict) to evaluate.
            evento: Dict with event data.

        Returns:
            True if the event matches all conditions.
        """
        condiciones = self._campo_regla(regla, "conditions")

        # If the root operator is and/or, evaluate as a group
        if isinstance(condiciones, dict) and "operator" in condiciones:
            operador = str(condiciones.get("operator")).lower()
            if operador in ("and", "or"):
                return self._evaluar_grupo(condiciones, evento)
            else:
                # Simple condition
                return self._evaluar_condicion(condiciones, evento)

        # If it is a list, all must be met (implicit AND)
        if isinstance(condiciones, list):
            return all(self._evaluar_condicion(c, evento) for c in condiciones)

        # Simple condition as a dict
        return self._evaluar_condicion(condiciones, evento)

    def _evaluar_grupo(self, grupo: dict, evento: dict) -> bool:
        """Evaluates a group of conditions (AND/OR).

        Args:
            grupo: Dict with "operator" and "conditions".
            evento: Dict with event data.

        Returns:
            Result of the logical evaluation.
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
        """Evaluates a single condition against an event.

        Args:
            condicion: Dict with "field", "operator", "value".
            evento: Dict with event data.

        Returns:
            True if the condition is met.

        Supported operators:
            - eq: equality (case-insensitive for strings)
            - neq: not equal
            - contains: the field contains the value (string)
            - gt, gte, lt, lte: numeric comparisons
            - in: the value is in a list
            - regex: the field matches a regular expression
            - exists: the field exists and is not None
            - not_exists: the field is None or does not exist
            - startswith: the field starts with the value
            - endswith: the field ends with the value
        """
        field = condicion.get("field")
        operator = condicion.get("operator", "eq")
        value = condicion.get("value")

        # Get the field value from the event
        valor_evento = evento.get(field) if field else None

        # Handle nested field with dot notation (e.g. "source_ip")
        if field and "." in field:
            partes = field.split(".")
            valor_evento = evento
            for parte in partes:
                if isinstance(valor_evento, dict):
                    valor_evento = valor_evento.get(parte)
                else:
                    valor_evento = None
                    break

        # Evaluate according to the operator
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
                logger.warning("Unknown operator: %s", operator)
                return False
        except (TypeError, ValueError, re.error) as e:
            logger.debug("Error evaluating condition %s: %s", condicion, e)
            return False

    def _eq(self, valor_evento: Any, value: Any) -> bool:
        """Case-insensitive equality comparison for strings."""
        if valor_evento is None:
            return False
        if isinstance(valor_evento, str) and isinstance(value, str):
            return valor_evento.lower() == value.lower()
        return valor_evento == value

    def _contains(self, valor_evento: Any, value: Any) -> bool:
        """Checks whether the field contains the value (case-insensitive)."""
        if valor_evento is None or value is None:
            return False
        return str(value).lower() in str(valor_evento).lower()

    def _compare(self, valor_evento: Any, value: Any, op) -> bool:
        """Numeric comparison."""
        if valor_evento is None or value is None:
            return False
        return op(float(valor_evento), float(value))

    def _in_list(self, valor_evento: Any, value: Any) -> bool:
        """Checks whether the event value is in the list of values.

        If value is a string, it is treated as a one-element list.
        """
        if valor_evento is None:
            return False
        if not isinstance(value, list):
            value = [value]
        valor_str = str(valor_evento).lower()
        return any(str(v).lower() == valor_str for v in value)

    def _regex(self, valor_evento: Any, pattern: str) -> bool:
        """Checks whether the field matches a regular expression."""
        if valor_evento is None or pattern is None:
            return False
        return bool(re.search(pattern, str(valor_evento)))

    def _startswith(self, valor_evento: Any, value: Any) -> bool:
        """Checks whether the field starts with the value."""
        if valor_evento is None or value is None:
            return False
        return str(valor_evento).lower().startswith(str(value).lower())

    def _endswith(self, valor_evento: Any, value: Any) -> bool:
        """Checks whether the field ends with the value."""
        if valor_evento is None or value is None:
            return False
        return str(valor_evento).lower().endswith(str(value).lower())

    async def _crear_alerta(
        self, regla: DetectionRule | dict, evento: dict
    ) -> dict | None:
        """Creates an alert using the registered callbacks.

        Args:
            regla: The rule that matched (object or dict).
            evento: The event that triggered the rule.

        Returns:
            Dict with the generated alert data.
        """
        datos_alerta = {
            "rule_id": self._campo_regla(regla, "id"),
            "title": self._campo_regla(regla, "alert_title"),
            "severity": self._campo_regla(regla, "alert_severity"),
            "description": (
                f"Rule '{self._campo_regla(regla, 'title')}' triggered by event "
                f"{evento.get('event_type', 'unknown')} from {evento.get('source', 'unknown')}: "
                f"{evento.get('description', 'no description')[:200]}"
            ),
            "status": "open",
            "event_count": 1,
            "first_event_at": evento.get("event_timestamp", datetime.now(UTC)),
            "last_event_at": evento.get("event_timestamp", datetime.now(UTC)),
        }

        # Run all registered callbacks
        if not self._callbacks:
            logger.debug("No callbacks registered — alert generated in memory")
            return datos_alerta

        for callback in self._callbacks:
            try:
                await callback(datos_alerta)
            except Exception as e:
                logger.error("Error in callback: %s", e, exc_info=True)

        return datos_alerta

    async def _ejecutar_callbacks_actualizar(self, datos: dict):
        """Runs all registered update callbacks.

        Args:
            datos: Dict with rule_id, event_count, last_event_at.
        """
        for callback in self._callbacks_actualizar:
            try:
                await callback(datos)
            except Exception as e:
                logger.error("Error in update callback: %s", e, exc_info=True)

    @property
    def reglas_activas(self) -> int:
        """Number of active rules loaded in memory."""
        return len(self._reglas)

    @property
    def ventanas_activas(self) -> int:
        """Number of active time windows."""
        ahora = datetime.now(UTC)
        return sum(1 for v in self._ventanas.values() if v["expires_at"] > ahora)
