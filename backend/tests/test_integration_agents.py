"""Tests de integración para AgentService, require_agent y admin API.

Verifica CRUD de agentes, generación de API key con hash bcrypt,
autenticación Bearer via require_agent, y endpoints admin.

Requiere PostgreSQL real via Testcontainers (fixture `session`).
"""

from datetime import UTC

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.services.agent_service import AgentService
from app.services.auth_service import AuthService

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def app():
    """Fixture que provee la instancia de la aplicación FastAPI."""
    from app.main import app

    return app


@pytest_asyncio.fixture
async def admin_client_and_token(session, app):
    """Crea admin user + JWT + httpx client con session override.

    Para evitar que el lifespan de la app y require_admin creen
    conexiones asyncpg propias (que pueden fallar en Windows),
    overrides la dependencia get_session para que use el mismo
    session del test.
    """
    from app.database import get_session

    # Crear admin user con la sesión del test
    service = AuthService(session)
    user = await service.crear_usuario(
        username="test_admin_agents",
        password="admin123",
        role="admin",
    )
    token = service.crear_token(user)

    # Override get_session para que use el session del test
    async def _override_get_session():
        return session

    app.dependency_overrides[get_session] = _override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, token

    app.dependency_overrides.clear()


# ── Helpers ────────────────────────────────────────────────────────────────


def _assert_valid_key_format(raw_key: str):
    """Verifica que la key tenga prefijo spy_ y formato url-safe base64."""
    assert raw_key.startswith("spy_"), "La API key debe empezar con spy_"
    assert len(raw_key) > 40, "La API key debe tener suficiente longitud"
    # Debe ser alfanumérico + guiones/guiones bajos después del spy_
    payload = raw_key[4:]
    assert all(c.isalnum() or c in "-_" for c in payload), (
        "La key debe ser url-safe base64"
    )


# ── AgentService Tests ─────────────────────────────────────────────────────


class TestCrearAgente:
    """Prueba creación de agentes con generación de API key."""

    @pytest.mark.asyncio
    async def test_crear_agente_simple(self, session):
        """Crea agente y verifica persistencia con key hasheada."""
        service = AgentService(session)
        agente, raw_key = await service.crear_agente(
            name="test-agent-01",
            hostname="server-01.example.com",
        )

        assert agente.id is not None
        assert isinstance(agente.id, int)
        assert agente.name == "test-agent-01"
        assert agente.hostname == "server-01.example.com"
        assert agente.active is True
        assert agente.version is None
        assert agente.last_seen is None

        # La key raw tiene formato correcto
        _assert_valid_key_format(raw_key)

        # El hash almacenado NO es la key plaintext
        assert agente.api_key_hash != raw_key

        # bcrypt verify funciona contra la key raw
        assert AuthService.verify_password(raw_key, agente.api_key_hash)

        # Timestamps
        assert agente.created_at is not None
        assert agente.updated_at is not None

    @pytest.mark.asyncio
    async def test_crear_agente_con_version(self, session):
        """Crea agente con versión explícita."""
        service = AgentService(session)
        agente, raw_key = await service.crear_agente(
            name="test-agent-v2",
            hostname="server-02.example.com",
            version="1.0.0",
        )

        assert agente.version == "1.0.0"
        _assert_valid_key_format(raw_key)

    @pytest.mark.asyncio
    async def test_crear_agente_duplicado_raise(self, session):
        """Crear agente con nombre existente lanza ValueError."""
        service = AgentService(session)
        await service.crear_agente(name="duplicado", hostname="host1")

        with pytest.raises(ValueError, match="ya existe"):
            await service.crear_agente(name="duplicado", hostname="host2")

    @pytest.mark.asyncio
    async def test_cada_agente_tiene_key_unica(self, session):
        """Cada agente recibe una API key diferente."""
        service = AgentService(session)
        _, key1 = await service.crear_agente(name="agent-a", hostname="host-a")
        _, key2 = await service.crear_agente(name="agent-b", hostname="host-b")

        assert key1 != key2, "Dos agentes NO deben tener la misma API key"
        _assert_valid_key_format(key1)
        _assert_valid_key_format(key2)


class TestObtenerPorApiKey:
    """Prueba búsqueda de agente por API key (para require_agent)."""

    @pytest.mark.asyncio
    async def test_obtener_por_api_key_valida(self, session):
        """Key válida retorna el agente."""
        service = AgentService(session)
        agente, raw_key = await service.crear_agente(
            name="key-test-agent",
            hostname="key-host",
        )

        encontrado = await service.obtener_por_api_key(raw_key)
        assert encontrado is not None
        assert encontrado.id == agente.id
        assert encontrado.name == "key-test-agent"

    @pytest.mark.asyncio
    async def test_obtener_por_api_key_invalida(self, session):
        """Key inválida retorna None."""
        service = AgentService(session)
        # Crear un agente con una key
        await service.crear_agente(name="other-agent", hostname="other-host")

        resultado = await service.obtener_por_api_key("spy_key_invalida_12345")
        assert resultado is None

    @pytest.mark.asyncio
    async def test_obtener_por_api_key_sin_agentes(self, session):
        """Sin agentes, cualquier key retorna None."""
        service = AgentService(session)
        resultado = await service.obtener_por_api_key("spy_alguna_key")
        assert resultado is None

    @pytest.mark.asyncio
    async def test_agente_desactivado_retorna_agente(self, session):
        """Agente con active=False aún se encuentra por API key.

        obtener_por_api_key no filtra por active — devuelve el agente
        incluso si está desactivado. El chequeo de estado lo hace
        require_agent (que retorna 403 si está inactivo).
        """
        service = AgentService(session)
        agente, raw_key = await service.crear_agente(
            name="inactive-agent",
            hostname="inactive-host",
        )

        # Desactivar
        await service.desactivar_agente(agente.id)
        await session.refresh(agente)
        assert agente.active is False

        # La key aún se reconoce, pero el agente está inactivo
        resultado = await service.obtener_por_api_key(raw_key)
        assert resultado is not None
        assert resultado.id == agente.id
        assert resultado.active is False

    @pytest.mark.asyncio
    async def test_obtener_por_api_key_con_varios_agentes(self, session):
        """Con múltiples agentes, encuentra el correcto por su key."""
        service = AgentService(session)
        _, key_a = await service.crear_agente(name="multi-a", hostname="host-a")
        await service.crear_agente(name="multi-b", hostname="host-b")
        _, key_c = await service.crear_agente(name="multi-c", hostname="host-c")

        encontrado = await service.obtener_por_api_key(key_a)
        assert encontrado is not None
        assert encontrado.name == "multi-a"

        encontrado_c = await service.obtener_por_api_key(key_c)
        assert encontrado_c is not None
        assert encontrado_c.name == "multi-c"


class TestListarAgentes:
    """Prueba listado de agentes."""

    @pytest.mark.asyncio
    async def test_listar_agentes_vacio(self, session):
        """Sin agentes, listar devuelve lista vacía y total 0."""
        service = AgentService(session)
        agentes, total = await service.listar_agentes()

        assert agentes == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_listar_agentes_con_datos(self, session):
        """Con agentes creados, listar devuelve todos."""
        service = AgentService(session)
        for i in range(3):
            await service.crear_agente(
                name=f"list-agent-{i}",
                hostname=f"host-{i}.example.com",
            )

        agentes, total = await service.listar_agentes()

        assert total == 3
        assert len(agentes) == 3
        # Debe incluir agentes activos e inactivos
        nombres = [a.name for a in agentes]
        assert "list-agent-0" in nombres
        assert "list-agent-2" in nombres

    @pytest.mark.asyncio
    async def test_listar_solo_activos(self, session):
        """Filtrar solo activos."""
        service = AgentService(session)
        await service.crear_agente(name="active-agent", hostname="host-a")
        agente_b, _ = await service.crear_agente(name="to-disable", hostname="host-b")
        await service.desactivar_agente(agente_b.id)

        agentes, total = await service.listar_agentes(solo_activos=True)

        assert total == 1
        assert agentes[0].name == "active-agent"

    @pytest.mark.asyncio
    async def test_listar_todos_incluye_inactivos(self, session):
        """Sin filtro, listar incluye agentes inactivos."""
        service = AgentService(session)
        await service.crear_agente(name="active-one", hostname="host-a")
        agente_b, _ = await service.crear_agente(name="to-disable-2", hostname="host-b")
        await service.desactivar_agente(agente_b.id)

        agentes, total = await service.listar_agentes()

        assert total == 2


class TestDesactivarAgente:
    """Prueba desactivación de agentes."""

    @pytest.mark.asyncio
    async def test_desactivar_agente_existente(self, session):
        """Desactivar agente existente cambia active a False."""
        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="to-deactivate",
            hostname="host",
        )

        resultado = await service.desactivar_agente(agente.id)
        assert resultado is True

        # Verificar en DB
        await session.refresh(agente)
        assert agente.active is False

    @pytest.mark.asyncio
    async def test_desactivar_agente_inexistente(self, session):
        """Desactivar agente que no existe retorna False."""
        service = AgentService(session)
        resultado = await service.desactivar_agente(99999)
        assert resultado is False

    @pytest.mark.asyncio
    async def test_desactivar_agente_ya_inactivo(self, session):
        """Desactivar agente ya inactivo no falla."""
        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="already-inactive",
            hostname="host",
        )

        await service.desactivar_agente(agente.id)
        resultado = await service.desactivar_agente(agente.id)
        assert resultado is True  # Sigue siendo exitoso


# ── require_agent Dependency Tests ─────────────────────────────────────────


class TestRequireAgent:
    """Prueba la dependency require_agent con Bearer token."""

    @pytest.mark.asyncio
    async def test_require_agent_token_valido(self, session):
        """Token Bearer válido retorna el agente."""
        from fastapi import Request

        from app.auth import require_agent

        service = AgentService(session)
        agente, raw_key = await service.crear_agente(
            name="require-agent-test",
            hostname="require-host",
        )

        # Simular Request con header Authorization
        scope = {
            "type": "http",
            "headers": [
                (b"authorization", f"Bearer {raw_key}".encode()),
            ],
        }
        request = Request(scope)

        # Inyectar service en request.state para la dependency
        # (require_agent usa AgentService via Depends, pero en test
        #  podemos mockear el session)
        resultado = await require_agent(request, session)
        assert resultado is not None
        assert resultado.id == agente.id
        assert resultado.name == "require-agent-test"

    @pytest.mark.asyncio
    async def test_require_agent_sin_token(self, session):
        """Sin header Authorization, require_agent lanza 401."""
        from fastapi import Request

        from app.auth import require_agent

        scope = {
            "type": "http",
            "headers": [],
        }
        request = Request(scope)

        with pytest.raises(HTTPException) as exc:
            await require_agent(request, session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_agent_token_invalido(self, session):
        """Token inválido lanza 401."""
        from fastapi import Request

        from app.auth import require_agent

        scope = {
            "type": "http",
            "headers": [
                (b"authorization", b"Bearer spy_key_invalida"),
            ],
        }
        request = Request(scope)

        with pytest.raises(HTTPException) as exc:
            await require_agent(request, session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_agent_agent_desactivado(self, session):
        """Agente desactivado con token válido lanza 403."""
        from fastapi import Request

        from app.auth import require_agent

        service = AgentService(session)
        agente, raw_key = await service.crear_agente(
            name="deactivated-agent-test",
            hostname="deactivated-host",
        )
        await service.desactivar_agente(agente.id)

        scope = {
            "type": "http",
            "headers": [
                (b"authorization", f"Bearer {raw_key}".encode()),
            ],
        }
        request = Request(scope)

        with pytest.raises(HTTPException) as exc:
            await require_agent(request, session)
        assert exc.value.status_code == 403


# ── Admin API Endpoint Tests ──────────────────────────────────────────────


class TestAdminAgentsAPI:
    """Prueba los endpoints GET/POST /api/admin/agents y PATCH deactivate.

    Para estos tests necesitamos un admin autenticado via cookie JWT.
    Nos apoyamos en el helper de login existente.
    """

    @pytest.mark.asyncio
    async def test_get_agents_sin_admin_retorna_401(self, app):
        """GET /api/admin/agents sin autenticación retorna 401."""
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/admin/agents")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_agents_vacio(self, admin_client_and_token):
        """GET /api/admin/agents con admin autenticado retorna lista vacía."""
        client, token = admin_client_and_token
        response = await client.get(
            "/api/admin/agents",
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["agents"] == []

    @pytest.mark.asyncio
    async def test_post_agent_crea_y_retorna_key(self, admin_client_and_token):
        """POST /api/admin/agents crea agente y retorna api_key_raw."""
        client, token = admin_client_and_token
        response = await client.post(
            "/api/admin/agents",
            json={"name": "api-test-agent", "hostname": "api-host"},
            cookies={"access_token": token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "api-test-agent"
        assert data["hostname"] == "api-host"
        assert data["active"] is True
        assert "api_key_raw" in data
        _assert_valid_key_format(data["api_key_raw"])
        # El hash NO debe estar en la respuesta
        assert "api_key_hash" not in data

    @pytest.mark.asyncio
    async def test_post_agent_duplicado_retorna_409(self, admin_client_and_token):
        """POST con nombre duplicado retorna 409."""
        client, token = admin_client_and_token
        await client.post(
            "/api/admin/agents",
            json={"name": "dup-agent", "hostname": "host1"},
            cookies={"access_token": token},
        )
        response = await client.post(
            "/api/admin/agents",
            json={"name": "dup-agent", "hostname": "host2"},
            cookies={"access_token": token},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_post_y_get_lista(self, admin_client_and_token):
        """Crear agente y luego listarlo."""
        client, token = admin_client_and_token
        await client.post(
            "/api/admin/agents",
            json={"name": "list-me", "hostname": "list-host"},
            cookies={"access_token": token},
        )

        response = await client.get(
            "/api/admin/agents",
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        nombres = [a["name"] for a in data["agents"]]
        assert "list-me" in nombres

    @pytest.mark.asyncio
    async def test_get_agents_no_expone_api_key_hash(self, admin_client_and_token):
        """GET /api/admin/agents nunca expone api_key_hash."""
        client, token = admin_client_and_token
        await client.post(
            "/api/admin/agents",
            json={"name": "no-hash-agent", "hostname": "no-hash"},
            cookies={"access_token": token},
        )

        response = await client.get(
            "/api/admin/agents",
            cookies={"access_token": token},
        )
        data = response.json()
        for agent in data["agents"]:
            assert "api_key_hash" not in agent, (
                "GET agents NO debe exponer api_key_hash"
            )
            assert "api_key_raw" not in agent, "GET agents NO debe exponer api_key_raw"

    @pytest.mark.asyncio
    async def test_patch_deactivate_agente(self, admin_client_and_token):
        """PATCH /api/admin/agents/{id}/deactivate desactiva el agente."""
        client, token = admin_client_and_token
        # Crear agente
        create_resp = await client.post(
            "/api/admin/agents",
            json={"name": "deactivate-me", "hostname": "deact-host"},
            cookies={"access_token": token},
        )
        agent_id = create_resp.json()["id"]

        # Desactivar
        response = await client.patch(
            f"/api/admin/agents/{agent_id}/deactivate",
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        assert "desactivado" in response.json()["mensaje"].lower()

        # Verificar que aparece como inactivo en el listado
        list_resp = await client.get(
            "/api/admin/agents",
            cookies={"access_token": token},
        )
        agente = next(a for a in list_resp.json()["agents"] if a["id"] == agent_id)
        assert agente["active"] is False

    @pytest.mark.asyncio
    async def test_patch_deactivate_inexistente_retorna_404(
        self, admin_client_and_token
    ):
        """PATCH a agente que no existe retorna 404."""
        client, token = admin_client_and_token
        response = await client.patch(
            "/api/admin/agents/99999/deactivate",
            cookies={"access_token": token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_post_agent_sin_name_retorna_422(self, admin_client_and_token):
        """POST sin name retorna 422."""
        client, token = admin_client_and_token
        response = await client.post(
            "/api/admin/agents",
            json={"hostname": "no-name"},
            cookies={"access_token": token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_post_agent_sin_hostname_retorna_422(self, admin_client_and_token):
        """POST sin hostname retorna 422."""
        client, token = admin_client_and_token
        response = await client.post(
            "/api/admin/agents",
            json={"name": "no-hostname"},
            cookies={"access_token": token},
        )
        assert response.status_code == 422


class TestObtenerAgentePorId:
    """Prueba GET /api/admin/agents/{id} — obtener agente por ID (AAD-5)."""

    @pytest.mark.asyncio
    async def test_obtener_agente_por_id_existente(self, session):
        """Obtener agente existente por ID retorna el agente sin hash."""
        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="get-by-id-test",
            hostname="get-host",
        )

        resultado = await service.obtener_por_id(agente.id)
        assert resultado is not None
        assert resultado.id == agente.id
        assert resultado.name == "get-by-id-test"
        assert resultado.hostname == "get-host"
        assert resultado.active is True
        # api_key_hash está presente en el modelo SQLAlchemy (es columna mapeada)
        # pero no se expone en el schema AgentRead — eso se verifica a nivel API endpoint
        assert resultado.api_key_hash is not None

    @pytest.mark.asyncio
    async def test_obtener_agente_por_id_inexistente(self, session):
        """Obtener agente con ID inexistente retorna None."""
        service = AgentService(session)
        resultado = await service.obtener_por_id(99999)
        assert resultado is None

    @pytest.mark.asyncio
    async def test_obtener_agente_por_id_api_endpoint(self, admin_client_and_token):
        """GET /api/admin/agents/{id} endpoint retorna el agente."""
        client, token = admin_client_and_token
        # Crear agente
        create_resp = await client.post(
            "/api/admin/agents",
            json={"name": "endpoint-get-test", "hostname": "endpoint-host"},
            cookies={"access_token": token},
        )
        agent_id = create_resp.json()["id"]

        # Obtener por ID
        response = await client.get(
            f"/api/admin/agents/{agent_id}",
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == agent_id
        assert data["name"] == "endpoint-get-test"
        assert data["hostname"] == "endpoint-host"
        assert "api_key_hash" not in data
        assert "api_key_raw" not in data

    @pytest.mark.asyncio
    async def test_get_agente_por_id_inexistente_404(self, admin_client_and_token):
        """GET /api/admin/agents/{id} con ID inexistente retorna 404."""
        client, token = admin_client_and_token
        response = await client.get(
            "/api/admin/agents/99999",
            cookies={"access_token": token},
        )
        assert response.status_code == 404


class TestActualizarAgente:
    """Prueba PUT /api/admin/agents/{id} — actualizar agente (AAD-3)."""

    @pytest.mark.asyncio
    async def test_actualizar_agente_campos(self, session):
        """Actualizar name y hostname de un agente."""
        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="update-test",
            hostname="old-host",
        )

        actualizado = await service.actualizar_agente(
            agente.id,
            name="updated-name",
            hostname="new-host",
        )
        assert actualizado is not None
        assert actualizado.name == "updated-name"
        assert actualizado.hostname == "new-host"
        assert actualizado.id == agente.id

    @pytest.mark.asyncio
    async def test_actualizar_agente_solo_name(self, session):
        """Actualizar solo el name mantiene hostname intacto."""
        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="partial-update",
            hostname="partial-host",
        )

        actualizado = await service.actualizar_agente(
            agente.id,
            name="solo-name",
        )
        assert actualizado is not None
        assert actualizado.name == "solo-name"
        assert actualizado.hostname == "partial-host"

    @pytest.mark.asyncio
    async def test_actualizar_agente_solo_hostname(self, session):
        """Actualizar solo hostname mantiene name intacto."""
        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="partial-host-update",
            hostname="host-old",
        )

        actualizado = await service.actualizar_agente(
            agente.id,
            hostname="host-new",
        )
        assert actualizado is not None
        assert actualizado.name == "partial-host-update"
        assert actualizado.hostname == "host-new"

    @pytest.mark.asyncio
    async def test_actualizar_agente_inexistente(self, session):
        """Actualizar agente inexistente retorna None."""
        service = AgentService(session)
        resultado = await service.actualizar_agente(99999, name="nope")
        assert resultado is None

    @pytest.mark.asyncio
    async def test_actualizar_agente_api_endpoint(self, admin_client_and_token):
        """PUT /api/admin/agents/{id} actualiza campos."""
        client, token = admin_client_and_token
        create_resp = await client.post(
            "/api/admin/agents",
            json={"name": "put-test-agent", "hostname": "put-host"},
            cookies={"access_token": token},
        )
        agent_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/admin/agents/{agent_id}",
            json={"name": "put-updated", "hostname": "put-new-host"},
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "put-updated"
        assert data["hostname"] == "put-new-host"
        assert "api_key_hash" not in data

    @pytest.mark.asyncio
    async def test_actualizar_agente_inexistente_404(self, admin_client_and_token):
        """PUT a agente inexistente retorna 404."""
        client, token = admin_client_and_token
        response = await client.put(
            "/api/admin/agents/99999",
            json={"name": "nope", "hostname": "nope"},
            cookies={"access_token": token},
        )
        assert response.status_code == 404


class TestEliminarAgente:
    """Prueba DELETE /api/admin/agents/{id} — eliminar agente (AAD-4)."""

    @pytest.mark.asyncio
    async def test_eliminar_agente_existente(self, session):
        """Eliminar agente existente retorna True."""
        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="delete-test",
            hostname="delete-host",
        )

        resultado = await service.eliminar_agente(agente.id)
        assert resultado is True

        # Verificar que ya no existe
        inexistente = await service.obtener_por_id(agente.id)
        assert inexistente is None

    @pytest.mark.asyncio
    async def test_eliminar_agente_inexistente(self, session):
        """Eliminar agente inexistente retorna False."""
        service = AgentService(session)
        resultado = await service.eliminar_agente(99999)
        assert resultado is False

    @pytest.mark.asyncio
    async def test_eliminar_agente_api_endpoint(self, admin_client_and_token):
        """DELETE /api/admin/agents/{id} elimina el agente."""
        client, token = admin_client_and_token
        create_resp = await client.post(
            "/api/admin/agents",
            json={"name": "delete-me-agent", "hostname": "delete-host"},
            cookies={"access_token": token},
        )
        agent_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/admin/agents/{agent_id}",
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        assert "eliminado" in response.json()["mensaje"].lower()

        # Verificar que ya no existe vía GET
        get_resp = await client.get(
            f"/api/admin/agents/{agent_id}",
            cookies={"access_token": token},
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_eliminar_agente_inexistente_404(self, admin_client_and_token):
        """DELETE a agente inexistente retorna 404."""
        client, token = admin_client_and_token
        response = await client.delete(
            "/api/admin/agents/99999",
            cookies={"access_token": token},
        )
        assert response.status_code == 404


class TestDesactivarInactivos:
    """Prueba desactivar_agentes_inactivos — auto-desactivación por timeout (AH-2)."""

    @pytest.mark.asyncio
    async def test_desactivar_agentes_stale(self, session):
        """Agentes con last_seen vencido se desactivan."""
        from datetime import datetime, timedelta

        from sqlalchemy import update

        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="stale-agent",
            hostname="stale-host",
        )

        # Poner last_seen hace 10 minutos (timeout default es 5)
        hace_10min = datetime.now(UTC) - timedelta(minutes=10)
        await session.execute(
            update(agente.__class__)
            .where(agente.__class__.id == agente.id)
            .values(last_seen=hace_10min)
        )
        await session.commit()

        desactivados = await service.desactivar_inactivos()
        assert desactivados >= 1

        await session.refresh(agente)
        assert agente.active is False

    @pytest.mark.asyncio
    async def test_no_desactiva_agentes_recientes(self, session):
        """Agentes con last_seen reciente NO se desactivan."""
        from datetime import datetime, timedelta

        from sqlalchemy import update

        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="fresh-agent",
            hostname="fresh-host",
        )

        # Poner last_seen hace 1 minuto (timeout default es 5)
        hace_1min = datetime.now(UTC) - timedelta(minutes=1)
        await session.execute(
            update(agente.__class__)
            .where(agente.__class__.id == agente.id)
            .values(last_seen=hace_1min)
        )
        await session.commit()

        desactivados = await service.desactivar_inactivos()
        assert desactivados == 0

        await session.refresh(agente)
        assert agente.active is True

    @pytest.mark.asyncio
    async def test_desactivar_inactivos_sin_last_seen(self, session):
        """Agentes sin last_seen (nunca hicieron heartbeat) se consideran inactivos."""
        service = AgentService(session)
        await service.crear_agente(
            name="no-heartbeat-agent",
            hostname="no-hb-host",
        )

        desactivados = await service.desactivar_inactivos()
        # last_seen is None, que es < now - timeout, debería desactivarse
        assert desactivados >= 1

    @pytest.mark.asyncio
    async def test_desactivar_inactivos_api_endpoint(
        self, admin_client_and_token, session
    ):
        """POST /api/admin/agents/desactivar-inactivos ejecuta la limpieza."""
        from datetime import datetime, timedelta

        from sqlalchemy import update

        client, token = admin_client_and_token

        # Crear agente stale
        service = AgentService(session)
        agente, _ = await service.crear_agente(
            name="stale-for-api",
            hostname="stale-api-host",
        )
        hace_10min = datetime.now(UTC) - timedelta(minutes=10)
        await session.execute(
            update(agente.__class__)
            .where(agente.__class__.id == agente.id)
            .values(last_seen=hace_10min)
        )
        await session.commit()

        response = await client.post(
            "/api/admin/agents/desactivar-inactivos",
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["desactivados"] >= 1

        await session.refresh(agente)
        assert agente.active is False
