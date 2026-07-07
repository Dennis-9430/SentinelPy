"""Tests unitarios para el motor de correlación.

Evalúa condiciones simples, grupos AND/OR/NOT, operadores,
caché de reglas, y el mecanismo de callbacks.
"""

import pytest

from app.services.engine import CorrelationEngine

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def engine():
    """Engine limpio sin reglas."""
    return CorrelationEngine()


@pytest.fixture
def regla_simple():
    """Regla que detecta intentos de login root."""
    return {
        "id": "rule-root-001",
        "title": "Intento de login como root",
        "conditions": {
            "operator": "AND",
            "conditions": [
                {"field": "event_type", "operator": "eq", "value": "authentication"},
                {"field": "user_name", "operator": "eq", "value": "root"},
            ],
        },
        "alert_title": "Login root detectado",
        "alert_severity": "high",
        "severity": "high",
        "correlation_window": 300,
        "status": "active",
    }


@pytest.fixture
def regla_multi_operador():
    """Regla con operadores mixtos (gt, contains, neq)."""
    return {
        "id": "rule-multi-002",
        "title": "Puerto sospechoso",
        "conditions": {
            "operator": "AND",
            "conditions": [
                {"field": "destination_port", "operator": "gt", "value": 1024},
                {"field": "protocol", "operator": "neq", "value": "TCP"},
                {"field": "description", "operator": "contains", "value": "suspicious"},
            ],
        },
        "alert_title": "Tráfico sospechoso detectado",
        "alert_severity": "medium",
        "severity": "medium",
        "correlation_window": 300,
        "status": "active",
    }


@pytest.fixture
def regla_or():
    """Regla con grupos OR anidados."""
    return {
        "id": "rule-or-003",
        "title": "Evento de seguridad crítico",
        "conditions": {
            "operator": "OR",
            "conditions": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "severity", "operator": "eq", "value": "critical"},
                        {
                            "field": "event_type",
                            "operator": "eq",
                            "value": "authentication",
                        },
                    ],
                },
                {
                    "operator": "AND",
                    "conditions": [
                        {"field": "severity", "operator": "eq", "value": "high"},
                        {
                            "field": "source_ip",
                            "operator": "in",
                            "value": ["10.0.0.1", "192.168.1.1"],
                        },
                    ],
                },
            ],
        },
        "alert_title": "Evento crítico de seguridad",
        "alert_severity": "critical",
        "severity": "critical",
        "correlation_window": 300,
        "status": "active",
    }


@pytest.fixture
def regla_not():
    """Regla con operador NOT."""
    return {
        "id": "rule-not-004",
        "title": "Tráfico no HTTP en puerto 80",
        "conditions": {
            "operator": "AND",
            "conditions": [
                {"field": "destination_port", "operator": "eq", "value": 80},
                {"field": "protocol", "operator": "not", "value": "TCP"},
            ],
        },
        "alert_title": "Puerto 80 no HTTP",
        "alert_severity": "low",
        "severity": "low",
        "correlation_window": 300,
        "status": "active",
    }


@pytest.fixture
def evento_root():
    """Evento de login root."""
    return {
        "event_type": "authentication",
        "user_name": "root",
        "severity": "high",
        "source": "test",
        "description": "Intento de login como root",
    }


@pytest.fixture
def evento_normal():
    """Evento normal que NO debería disparar la regla root."""
    return {
        "event_type": "authentication",
        "user_name": "admin",
        "severity": "info",
        "source": "test",
        "description": "Login normal de admin",
    }


@pytest.fixture
def evento_sospechoso():
    """Evento con puerto alto y descripción sospechosa."""
    return {
        "destination_port": 4444,
        "protocol": "UDP",
        "description": "conexión suspicious detectada",
        "severity": "medium",
    }


@pytest.fixture
def evento_critico():
    """Evento crítico que dispara el grupo OR."""
    return {
        "severity": "critical",
        "event_type": "authentication",
        "source_ip": "10.0.0.1",
    }


@pytest.fixture
def evento_puerto80():
    """Evento en puerto 80 con protocolo no TCP."""
    return {
        "destination_port": 80,
        "protocol": "UDP",
    }


# ── Tests de evaluación de condiciones ───────────────────────────────────


class TestEvaluacionCondiciones:
    """Prueba la evaluación de condiciones individuales."""

    def test_eq_cumple(self, engine):
        """eq: el valor coincide."""
        assert engine._evaluar_condicion(
            {"field": "severity", "operator": "eq", "value": "high"},
            {"severity": "high"},
        )

    def test_eq_no_cumple(self, engine):
        """eq: el valor NO coincide."""
        assert not engine._evaluar_condicion(
            {"field": "severity", "operator": "eq", "value": "critical"},
            {"severity": "high"},
        )

    def test_neq_cumple(self, engine):
        """neq: el valor es diferente."""
        assert engine._evaluar_condicion(
            {"field": "protocol", "operator": "neq", "value": "TCP"},
            {"protocol": "UDP"},
        )

    def test_contains_cumple(self, engine):
        """contains: el texto contiene el substring."""
        assert engine._evaluar_condicion(
            {"field": "description", "operator": "contains", "value": "root"},
            {"description": "Intento de login como root"},
        )

    def test_contains_no_cumple(self, engine):
        """contains: no contiene el substring."""
        assert not engine._evaluar_condicion(
            {"field": "description", "operator": "contains", "value": "admin"},
            {"description": "Intento de login como root"},
        )

    def test_gt_cumple(self, engine):
        """gt: valor mayor que."""
        assert engine._evaluar_condicion(
            {"field": "destination_port", "operator": "gt", "value": 1024},
            {"destination_port": 4444},
        )

    def test_lt_cumple(self, engine):
        """lt: valor menor que."""
        assert engine._evaluar_condicion(
            {"field": "destination_port", "operator": "lt", "value": 1024},
            {"destination_port": 80},
        )

    def test_in_cumple(self, engine):
        """in: el valor está en la lista."""
        assert engine._evaluar_condicion(
            {
                "field": "source_ip",
                "operator": "in",
                "value": ["10.0.0.1", "192.168.1.1"],
            },
            {"source_ip": "10.0.0.1"},
        )

    def test_not_cumple(self, engine):
        """not: el valor NO debe ser igual."""
        assert engine._evaluar_condicion(
            {"field": "protocol", "operator": "not", "value": "TCP"},
            {"protocol": "UDP"},
        )

    def test_not_falla(self, engine):
        """not: falla si el valor es igual."""
        assert not engine._evaluar_condicion(
            {"field": "protocol", "operator": "not", "value": "TCP"},
            {"protocol": "TCP"},
        )

    def test_regex_cumple(self, engine):
        """regex: el patrón coincide."""
        assert engine._evaluar_condicion(
            {"field": "source_ip", "operator": "regex", "value": r"^10\.\d+\.\d+\.\d+"},
            {"source_ip": "10.0.0.1"},
        )

    def test_campo_ausente(self, engine):
        """Si el campo no existe en el evento, la condición falla."""
        assert not engine._evaluar_condicion(
            {"field": "user_name", "operator": "eq", "value": "root"},
            {"severity": "high"},
        )

    def test_valor_ausente_evento_gt(self, engine):
        """Si el campo falta, gt falla en lugar de tirar error."""
        assert not engine._evaluar_condicion(
            {"field": "source_port", "operator": "gt", "value": 1000},
            {},
        )


# ── Tests de evaluación de grupos ────────────────────────────────────────


class TestEvaluacionGrupos:
    """Prueba la evaluación de grupos AND/OR/NOT."""

    def test_and_todo_cumple(self, engine, regla_simple, evento_root):
        """AND: todas las condiciones se cumplen."""
        assert engine._evaluar_grupo(regla_simple["conditions"], evento_root)

    def test_and_una_falla(self, engine, regla_simple, evento_normal):
        """AND: una condición falla → todo falla."""
        assert not engine._evaluar_grupo(regla_simple["conditions"], evento_normal)

    def test_and_multi_operador_cumple(
        self, engine, regla_multi_operador, evento_sospechoso
    ):
        """AND con múltiples operadores."""
        assert engine._evaluar_grupo(
            regla_multi_operador["conditions"], evento_sospechoso
        )

    def test_or_primera_cumple(self, engine, regla_or, evento_critico):
        """OR: la primera rama cumple."""
        assert engine._evaluar_grupo(regla_or["conditions"], evento_critico)

    def test_or_segunda_cumple(self, engine, regla_or):
        """OR: la segunda rama cumple con IP en lista."""
        evento = {"severity": "high", "source_ip": "192.168.1.1"}
        assert engine._evaluar_grupo(regla_or["conditions"], evento)

    def test_or_ninguna_cumple(self, engine, regla_or):
        """OR: ninguna rama cumple."""
        evento = {"severity": "low", "source_ip": "8.8.8.8"}
        assert not engine._evaluar_grupo(regla_or["conditions"], evento)

    def test_not_cumple(self, engine, regla_not, evento_puerto80):
        """NOT: el campo no coincide."""
        assert engine._evaluar_grupo(regla_not["conditions"], evento_puerto80)

    def test_not_falla(self, engine, regla_not):
        """NOT: falla cuando el protocolo SÍ es TCP."""
        evento = {"destination_port": 80, "protocol": "TCP"}
        assert not engine._evaluar_grupo(regla_not["conditions"], evento)


# ── Tests del flujo completo ─────────────────────────────────────────────


class TestEngineCompleto:
    """Prueba el flujo evaluate() con reglas cargadas y callbacks."""

    @pytest.mark.asyncio
    async def test_evento_dispara_regla(self, engine, regla_simple, evento_root):
        """Un evento que cumple la regla genera una alerta."""
        engine.cargar_reglas([regla_simple])
        alertas = await engine.evaluate(evento_root)
        assert len(alertas) == 1
        assert alertas[0]["title"] == "Login root detectado"
        assert alertas[0]["severity"] == "high"
        assert alertas[0]["rule_id"] == "rule-root-001"

    @pytest.mark.asyncio
    async def test_evento_no_dispara(self, engine, regla_simple, evento_normal):
        """Un evento normal NO genera alertas."""
        engine.cargar_reglas([regla_simple])
        alertas = await engine.evaluate(evento_normal)
        assert len(alertas) == 0

    @pytest.mark.asyncio
    async def test_multiples_reglas(self, engine, regla_simple, regla_multi_operador):
        """Un evento puede disparar varias reglas."""
        engine.cargar_reglas([regla_simple, regla_multi_operador])
        # Un evento que dispara ambas
        evento = {
            "event_type": "authentication",
            "user_name": "root",
            "destination_port": 8080,
            "protocol": "UDP",
            "description": "conexión suspicious",
        }
        alertas = await engine.evaluate(evento)
        assert len(alertas) == 2

    @pytest.mark.asyncio
    async def test_callback_ejecutado(self, engine, regla_simple, evento_root):
        """El callback registrado se ejecuta cuando se genera una alerta."""
        callbacks = []

        async def mi_callback(alerta):
            callbacks.append(alerta)
            return alerta

        engine.registrar_callback(mi_callback)
        engine.cargar_reglas([regla_simple])
        await engine.evaluate(evento_root)
        assert len(callbacks) == 1
        assert callbacks[0]["title"] == "Login root detectado"

    @pytest.mark.asyncio
    async def test_multiples_callbacks(self, engine, regla_simple, evento_root):
        """Múltiples callbacks registrados."""
        resultados = []

        async def cb1(a):
            resultados.append(f"cb1-{a['title']}")
            return a

        async def cb2(a):
            resultados.append(f"cb2-{a['title']}")
            return a

        engine.registrar_callback(cb1)
        engine.registrar_callback(cb2)
        engine.cargar_reglas([regla_simple])
        await engine.evaluate(evento_root)
        assert len(resultados) == 2

    @pytest.mark.asyncio
    async def test_recargar_reglas(self, engine):
        """cargar_reglas reemplaza el caché completamente."""
        r1 = {
            "id": "rule-1",
            "title": "Regla 1",
            "conditions": {"field": "severity", "operator": "eq", "value": "critical"},
            "alert_title": "Alerta 1",
            "alert_severity": "high",
            "severity": "high",
            "correlation_window": 300,
            "status": "active",
        }
        r2 = {
            "id": "rule-2",
            "title": "Regla 2",
            "conditions": {"field": "severity", "operator": "eq", "value": "high"},
            "alert_title": "Alerta 2",
            "alert_severity": "medium",
            "severity": "medium",
            "correlation_window": 300,
            "status": "active",
        }

        engine.cargar_reglas([r1])
        assert engine.reglas_activas == 1

        engine.cargar_reglas([r2])
        assert engine.reglas_activas == 1  # Reemplazó, no acumuló

    @pytest.mark.asyncio
    async def test_regla_inactiva_no_evalua(self, engine):
        """Reglas con status != active se ignoran."""
        regla = {
            "id": "rule-disabled",
            "title": "Desactivada",
            "conditions": {"field": "severity", "operator": "eq", "value": "critical"},
            "alert_title": "No debería",
            "alert_severity": "high",
            "severity": "high",
            "correlation_window": 300,
            "status": "disabled",
        }
        engine.cargar_reglas([regla])
        assert engine.reglas_activas == 0

    def test_propiedad_reglas_activas(self, engine, regla_simple):
        """reglas_activas refleja el conteo."""
        assert engine.reglas_activas == 0
        engine.cargar_reglas([regla_simple])
        assert engine.reglas_activas == 1


# ── Tests de operadores borde ────────────────────────────────────────────


class TestOperadoresBorde:
    """Casos borde para los operadores."""

    def test_exists_cumple(self, engine):
        """exists: el campo existe en el evento."""
        assert engine._evaluar_condicion(
            {"field": "source_ip", "operator": "exists"},
            {"source_ip": "10.0.0.1"},
        )

    def test_exists_no_cumple(self, engine):
        """exists: el campo no existe."""
        assert not engine._evaluar_condicion(
            {"field": "source_ip", "operator": "exists"},
            {"severity": "high"},
        )

    def test_gt_con_string_no_numero(self, engine):
        """gt con valor string: falla sin tirar error."""
        assert not engine._evaluar_condicion(
            {"field": "severity", "operator": "gt", "value": 5},
            {"severity": "high"},
        )

    def test_in_con_valor_no_lista(self, engine):
        """in con valor que no es lista: trata el string como lista."""
        evento = {"severity": "critical"}
        assert engine._evaluar_condicion(
            {"field": "severity", "operator": "in", "value": "critical"},
            evento,
        )


# ── Tests de correlación temporal ─────────────────────────────────────────


class TestCorrelacionTemporal:
    """Prueba el manejo de ventanas temporales en el engine."""

    @pytest.fixture
    def regla_con_ventana(self):
        """Regla con correlation_window de 300 segundos."""
        return {
            "id": "rule-window-001",
            "title": "Ventana temporal",
            "conditions": {"field": "severity", "operator": "eq", "value": "critical"},
            "alert_title": "Alerta con ventana",
            "alert_severity": "high",
            "severity": "high",
            "correlation_window": 300,
            "status": "active",
        }

    @pytest.fixture
    def regla_sin_ventana(self):
        """Regla SIN correlation_window (alerta inmediata)."""
        return {
            "id": "rule-nowindow-002",
            "title": "Sin ventana",
            "conditions": {"field": "severity", "operator": "eq", "value": "critical"},
            "alert_title": "Alerta inmediata",
            "alert_severity": "high",
            "severity": "high",
            "status": "active",
        }

    @pytest.mark.asyncio
    async def test_primer_evento_crea_alerta(self, engine, regla_con_ventana):
        """El primer match con ventana crea una alerta."""
        engine.cargar_reglas([regla_con_ventana])
        alertas = await engine.evaluate({"severity": "critical"})
        assert len(alertas) == 1
        assert alertas[0]["title"] == "Alerta con ventana"
        assert alertas[0]["event_count"] == 1

    @pytest.mark.asyncio
    async def test_segundo_evento_no_crea_alerta(self, engine, regla_con_ventana):
        """Segundo match dentro de la ventana NO crea nueva alerta."""
        engine.cargar_reglas([regla_con_ventana])

        # Primer match: crea alerta
        alertas1 = await engine.evaluate({"severity": "critical"})
        assert len(alertas1) == 1

        # Segundo match (dentro de ventana): NO crea alerta
        alertas2 = await engine.evaluate({"severity": "critical"})
        assert len(alertas2) == 0

    @pytest.mark.asyncio
    async def test_update_callback_ejecutado(self, engine, regla_con_ventana):
        """El callback de actualización se ejecuta en el segundo match."""
        updates = []

        async def cb_update(datos):
            updates.append(datos)

        engine.registrar_callback_actualizar(cb_update)
        engine.cargar_reglas([regla_con_ventana])

        # Primer match: callback de creación
        await engine.evaluate({"severity": "critical"})
        assert len(updates) == 0  # No se llamó al update

        # Segundo match: callback de actualización
        await engine.evaluate({"severity": "critical"})
        assert len(updates) == 1
        assert updates[0]["rule_id"] == "rule-window-001"
        assert updates[0]["event_count"] == 2

    @pytest.mark.asyncio
    async def test_event_count_se_acumula(self, engine, regla_con_ventana):
        """El contador event_count se incrementa con cada match."""
        engine.cargar_reglas([regla_con_ventana])
        updates = []

        async def cb_update(datos):
            updates.append(datos["event_count"])

        engine.registrar_callback_actualizar(cb_update)

        # 3 matches dentro de la ventana
        await engine.evaluate({"severity": "critical"})  # Crea alerta (count=1)
        await engine.evaluate({"severity": "critical"})  # Update (count=2)
        await engine.evaluate({"severity": "critical"})  # Update (count=3)

        assert updates == [2, 3]

    @pytest.mark.asyncio
    async def test_regla_sin_ventana_siempre_crea_alerta(
        self, engine, regla_sin_ventana
    ):
        """Regla sin correlation_window: cada match crea alerta."""
        engine.cargar_reglas([regla_sin_ventana])

        # Primer match
        a1 = await engine.evaluate({"severity": "critical"})
        assert len(a1) == 1

        # Segundo match: también crea alerta (sin ventana)
        a2 = await engine.evaluate({"severity": "critical"})
        assert len(a2) == 1

    @pytest.mark.asyncio
    async def test_ventanas_activas_property(self, engine, regla_con_ventana):
        """ventanas_activas refleja las ventanas abiertas."""
        assert engine.ventanas_activas == 0

        engine.cargar_reglas([regla_con_ventana])
        await engine.evaluate({"severity": "critical"})

        assert engine.ventanas_activas == 1

    @pytest.mark.asyncio
    async def test_recarga_limpia_ventanas(self, engine, regla_con_ventana):
        """cargar_reglas() limpia las ventanas activas."""
        engine.cargar_reglas([regla_con_ventana])
        await engine.evaluate({"severity": "critical"})
        assert engine.ventanas_activas == 1

        # Recargar (misma regla)
        engine.cargar_reglas([regla_con_ventana])
        assert engine.ventanas_activas == 0

    @pytest.mark.asyncio
    async def test_ventana_expirada_crea_nueva_alerta(self, engine, regla_con_ventana):
        """Cuando la ventana expira, el próximo match crea una alerta nueva."""
        engine.cargar_reglas([regla_con_ventana])

        # Modificar la regla para que tenga ventana de 0 segundos (expirada)
        regla_expirada = dict(regla_con_ventana)
        regla_expirada["correlation_window"] = 0

        engine.cargar_reglas([regla_expirada])
        await engine.evaluate({"severity": "critical"})  # Crea alerta

        # La ventana expira instantáneamente (0 segundos)
        import asyncio

        await asyncio.sleep(0.01)

        alertas = await engine.evaluate({"severity": "critical"})
        assert len(alertas) == 1  # Nueva alerta

    @pytest.mark.asyncio
    async def test_regla_sin_id_no_ventana(self, engine):
        """Regla sin ID no usa correlación temporal (edge case)."""
        regla = {
            "title": "Sin ID",
            "conditions": {"field": "severity", "operator": "eq", "value": "critical"},
            "alert_title": "No ID",
            "alert_severity": "high",
            "severity": "high",
            "correlation_window": 300,
            "status": "active",
        }
        engine.cargar_reglas([regla])

        # Sin ID: siempre crea alerta inmediata
        a1 = await engine.evaluate({"severity": "critical"})
        assert len(a1) == 1

        a2 = await engine.evaluate({"severity": "critical"})
        assert len(a2) == 1  # No hay ventana, siempre crea
