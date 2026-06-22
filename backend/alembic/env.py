"""Configuración del entorno de Alembic para migraciones.

Alembic usa este archivo para saber cómo conectarse a la base de datos
y qué modelos considerar al generar migraciones automáticas.
"""

import sys
from pathlib import Path
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Agregar el directorio raíz del backend al path para que Alembic
# pueda importar los módulos de la aplicación
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Cargar configuración de alembic.ini
config = context.config

# Configurar logging si existe la sección [loggers] en alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

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


def run_migrations_online():
    """Ejecuta migraciones conectándose a la base de datos.

    Es el modo normal de uso. Conecta, calcula el delta,
    y aplica los cambios.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
