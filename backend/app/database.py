"""Configuración de la base de datos PostgreSQL con SQLAlchemy asíncrono.

Usamos asyncpg como driver asíncrono para no bloquear el event loop
de FastAPI cuando hacemos consultas a la base de datos.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

# ── Engine asíncrono ─────────────────────────────────────────────────────
# create_async_engine reemplaza a create_engine de SQLAlchemy sync.
# echo=True logea todas las queries (útil en desarrollo).
engine = create_async_engine(settings.database_url, echo=settings.debug)

# ── Session factory ──────────────────────────────────────────────────────
# async_sessionmaker crea sesiones asíncronas que se usan en los endpoints.
# expire_on_commit=False evita que SQLAlchemy invalide objetos después de commit.
async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncSession:
    """Dependency de FastAPI que provee una sesión de base de datos.

    Se usa como: Depends(get_session) en cada endpoint.
    El context manager asegura que la sesión se cierre aunque haya errores.
    """
    async with async_session() as session:
        yield session
