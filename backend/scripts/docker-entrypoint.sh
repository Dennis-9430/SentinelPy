#!/bin/sh
# Entrypoint para el contenedor de SentinelPy
# Ejecuta migraciones de Alembic antes de iniciar la app

set -e

echo "=== SentinelPy — Entrypoint ==="
echo "Ejecutando migraciones de base de datos..."

# Ejecutar migraciones Alembic
alembic upgrade head

echo "Migraciones aplicadas correctamente."

# Ejecutar el comando que recibe como argumento (CMD del Dockerfile)
exec "$@"
