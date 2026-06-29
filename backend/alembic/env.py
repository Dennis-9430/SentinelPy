"""Configuración del entorno de Alembic para migraciones.

Alembic usa este archivo para saber cómo conectarse a la base de datos
y qué modelos considerar al generar migraciones automáticas.

Soporta URLs asíncronas (postgresql+asyncpg://) usando create_async_engine
en vez del engine_from_config síncrono que usan los ejemplos por defecto.
"""

import asyncio
import os
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# Agregar el directorio raíz del backend al path para que Alembic
# pueda importar los módulos de la aplicación
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Cargar configuración de alembic.ini
config = context.config

# Configurar logging si existe la sección [loggers] en alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Permitir override de la URL via DATABASE_URL (usado en Docker/producción)
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Importar la base para que Alembic detecte los modelos
from app.models.base import Base  # noqa: E402

# target_metadata le dice a Alembic qué modelos considerar
# para generar migraciones automáticas (--autogenerate)
target_metadata = Base.metadata


def run_migrations_offline():
    """Ejecuta migraciones en modo 'offline'.

    Genera el SQL sin conectarse a la base de datos.
    Útil para revisar el SQL antes de aplicarlo.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Configura el contexto de Alembic y ejecuta las migraciones.

    Separada de run_migrations_online para poder llamarla
    tanto desde sync como desde async run_sync.
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Ejecuta migraciones conectándose a la base de datos.

    Usa create_async_engine para soportar URLs con driver asíncrono
    (postgresql+asyncpg://) que es lo que usa la aplicación.

    El patrón asyncio.run() + run_sync es el recomendado
    por la documentación de Alembic para proyectos async.
    """
    url = config.get_main_option("sqlalchemy.url")
    connectable = create_async_engine(url)

    async def run_async():
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    asyncio.run(run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
