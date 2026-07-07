"""Configuración centralizada para tests de integración con Testcontainers.

Levanta un contenedor PostgreSQL 16 efímero, corre las migraciones
de Alembic, y provee fixtures de SQLAlchemy async para todos los
tests que necesiten base de datos real.

Arquitectura:
  postgres_container (session) → sync_url (session) → run_migrations (session)
                                                       ↓
                                              async_engine (session)
                                                       ↓
                                              session (function)

Los tests unitarios comunes NO usan estas fixtures — solo los archivos
test_integration_*.py solicitan explícitamente la fixture `session`.
"""

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.config import settings

# ── PostgreSQL Testcontainer ─────────────────────────────────────────────


@pytest.fixture(scope="session")
def postgres_container():
    """Levanta PostgreSQL 16 Alpine efímero.

    Configura settings.database_url automáticamente para que apunte
    al contenedor. El contenedor se destruye al finalizar la sesión.
    """
    with PostgresContainer("postgres:16-alpine") as pg:
        # La URL por defecto incluye driver psycopg2; necesitamos asyncpg
        sync_url = pg.get_connection_url(driver=None)
        async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://")

        # Override global de settings para que toda la app apunte al test DB
        settings.database_url = async_url

        yield pg, sync_url


@pytest.fixture(scope="session")
def sync_url(postgres_container) -> str:
    """URL síncrona (sin driver async) para Alembic."""
    _, sync_url = postgres_container
    return sync_url


@pytest.fixture(scope="session")
def run_migrations(sync_url):
    """Ejecuta todas las migraciones de Alembic contra el testcontainer.

    Corre una sola vez al inicio de la sesión de tests.
    """
    from alembic.config import Config

    from alembic import command

    backend_dir = Path(__file__).resolve().parent.parent
    alembic_ini = str(backend_dir / "alembic.ini")
    alembic_cfg = Config(alembic_ini)
    # Alembic's script_location is relative to CWD, not the ini file location.
    # Force it to an absolute path so it works regardless of where pytest runs.
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    # env.py reads DATABASE_URL from the environment and overrides the URL.
    # During tests, the testcontainer URL is set via settings.database_url,
    # so we must prevent env.py from reading the CI/production DATABASE_URL.
    old_db_url = os.environ.pop("DATABASE_URL", None)
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(alembic_cfg, "head")
    if old_db_url is not None:
        os.environ["DATABASE_URL"] = old_db_url
    return True  # señal de que las tablas están listas


# ── SQLAlchemy async engine ──────────────────────────────────────────────

TABLAS = ["agents", "alerts", "events", "rules", "users"]


@pytest_asyncio.fixture
async def async_engine(run_migrations):
    """Engine asíncrono por test — apunta al PostgreSQL del testcontainer.

    Se crea un engine por test para mantener coherencia de event loop
    (cada test corre en su propio loop). El pool es liviano de crear.
    """
    engine = create_async_engine(settings.database_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Sesión async de SQLAlchemy — tabla limpia por test.

    Antes de cada test ejecuta TRUNCATE en todas las tablas para
    garantizar aislamiento total entre tests.
    """
    async with async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )() as ses:
        for tabla in TABLAS:
            await ses.execute(text(f"TRUNCATE TABLE {tabla} CASCADE"))
        await ses.commit()
        yield ses
