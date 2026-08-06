"""PostgreSQL database configuration with async SQLAlchemy.

We use asyncpg as the async driver so we do not block the FastAPI
event loop when querying the database.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# ── Async engine ─────────────────────────────────────────────────────
# create_async_engine replaces the sync create_engine from SQLAlchemy.
# echo=True logs all queries (useful in development).
engine = create_async_engine(settings.database_url, echo=settings.debug)

# ── Session factory ──────────────────────────────────────────────────────
# async_sessionmaker creates async sessions used by the endpoints.
# expire_on_commit=False keeps SQLAlchemy from invalidating objects after commit.
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """FastAPI dependency that provides a database session.

    Used as: Depends(get_session) in every endpoint.
    The context manager ensures the session is closed even on errors.
    """
    async with async_session() as session:
        yield session
