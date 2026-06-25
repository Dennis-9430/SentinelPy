# Fase 08: Configuración Productiva

## Objetivo

Transformar SentinelPy de un proyecto de desarrollo a una aplicación
instalable y desplegable. Esto incluye: Docker multi-stage para imágenes
más chicas y seguras, entrypoint con migraciones automáticas, separación
de perfiles dev/prod, healthchecks, configuración vía entorno, y una
guía de instalación paso a paso.

## Arquitectura

```
                    ┌──────────────────────────────────────┐
                    │          docker-compose.yml          │
                    │                                      │
                    │  ┌─────────────┐  ┌──────────────┐  │
                    │  │     db      │  │     api      │  │
                    │  │ PostgreSQL  │  │  FastAPI     │  │
                    │  │ 16-alpine   │  │  multi-stage │  │
                    │  │             │  │              │  │
                    │  │ healthcheck │  │ healthcheck  │  │
                    │  │ pg_isready  │  │ GET /health  │  │
                    │  │ restart     │  │ restart      │  │
                    │  │ unless-stop │  │ unless-stop  │  │
                    │  └──────┬──────┘  └──────┬───────┘  │
                    │         │                 │          │
                    │         └──red interna────┘          │
                    │                                      │
                    │  Volumen: pgdata (datos persistentes) │
                    └──────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │       Dockerfile (multi-stage)        │
                    │                                      │
                    │  Stage 1: builder                    │
                    │    python:3.13-slim                   │
                    │    pip install --user -r requirements │
                    │                                      │
                    │  Stage 2: runtime                    │
                    │    python:3.13-slim                   │
                    │    COPY --from=builder /root/.local   │
                    │    COPY application code              │
                    │    USER sentinel (no-root)            │
                    │    ENTRYPOINT scripts/entrypoint.sh   │
                    └──────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │      docker-entrypoint.sh            │
                    │                                      │
                    │  1. alembic upgrade head             │
                    │  2. exec "$@" (CMD del Dockerfile)   │
                    └──────────────────────────────────────┘
```

## Componentes

### 1. Dockerfile Multi-Stage

**Antes:** Single-stage, copiaba todo, corría como root, sin entrypoint.

**Ahora:** Dos etapas que separan la compilación de la ejecución.

**Stage 1 — Builder:**

```dockerfile
FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
```

- Usa `--user` para instalar en `/root/.local` en lugar del sistema
- Solo copia `requirements.txt` primero para aprovechar la cache de Docker
- Se reconstruye solo si cambian las dependencias

**Stage 2 — Runtime:**

```dockerfile
FROM python:3.13-slim AS runtime
WORKDIR /app

# Usuario no-root
RUN addgroup --system --gid 1001 sentinel && \
    adduser --system --uid 1001 sentinel

# Copiar dependencias desde builder
COPY --from=builder /root/.local /root/.local

# Copiar código fuente
COPY . .

# Entrypoint con migraciones automáticas
RUN chmod +x scripts/docker-entrypoint.sh
ENV PATH=/root/.local/bin:$PATH

USER sentinel
EXPOSE 8000
ENTRYPOINT ["scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Ventajas del multi-stage:**
- **Imagen más chica**: solo incluye runtime, no las herramientas de build
- **No-root**: el contenedor corre como `sentinel`, no como root (mejores prácticas de seguridad)
- **Cache eficiente**: las dependencias se cachean por separado del código

### 2. Entrypoint Script

```bash
#!/bin/sh
set -e

echo "=== SentinelPy — Entrypoint ==="
echo "Ejecutando migraciones de base de datos..."

alembic upgrade head

echo "Migraciones aplicadas correctamente."

exec "$@"
```

**`set -e`**: si algún comando falla, el script se detiene (fail-fast).
**`exec "$@"`**: reemplaza el proceso actual con el CMD del Dockerfile.
Esto es crítico porque:
- El CMD (uvicorn) se convierte en PID 1
- Recibe señales (`SIGTERM`, `SIGINT`) correctamente
- Docker puede hacer `docker stop` graceful

### 3. docker-compose.yml

Refactorizado para usar variables de entorno con defaults seguros:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-sentinelpy}
      POSTGRES_USER: ${POSTGRES_USER:-sentinel}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-sentinel_dev}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-sentinel} -d ${POSTGRES_DB:-sentinelpy}"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "${API_PORT:-8000}:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-sentinel}:${POSTGRES_PASSWORD:-sentinel_dev}@db:5432/${POSTGRES_DB:-sentinelpy}
      SECRET_KEY: ${SECRET_KEY:-change-me-in-production}
      DEBUG: ${DEBUG:-false}
      # ... todas las variables de entorno de Fase 6 y 7
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    restart: unless-stopped
```

**Cambios clave respecto a la versión anterior:**

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| Credenciales DB | Hardcodeadas | Variables `${VAR:-default}` |
| Hot-reload | Siempre activo | Solo en dev profile |
| Volumen bind | `./backend:/app` | Solo en dev |
| Healthcheck API | No tenía | `curl -f http://localhost:8000/health` |
| Restart policy | No tenía | `unless-stopped` |
| Logging | Default | `json-file` con rotación |
| Command | `uvicorn --reload` | Desde entrypoint |

### 4. docker-compose.prod.yml

Override para producción que modifica solo lo necesario:

```yaml
services:
  db:
    ports: []  # No exponer PostgreSQL al host

  api:
    environment:
      DEBUG: "false"
```

**Cómo funciona el override:**

Docker Compose mergea configs en orden:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

- `docker-compose.yml` define la config base (completa, con defaults seguros)
- `docker-compose.prod.yml` sobreescribe solo diferencias productivas

Esto evita duplicar config y mantiene un solo source of truth.

### 5. Healthchecks

**PostgreSQL:**

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U sentinel -d sentinelpy"]
  interval: 5s
  timeout: 3s
  retries: 5
```

- `pg_isready` es el comando estándar de PostgreSQL para verificar conexión
- Intervalo de 5s para detectar rápido que la DB está lista
- La API espera con `condition: service_healthy`

**API:**

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 15s
```

- Usa el endpoint `/health` que ya existía (devuelve `{"status": "healthy"}`)
- `start_period: 15s` le da tiempo a la app para inicializarse (migraciones, seed admin)
- `-f` hace que curl falle si el código HTTP es error

### 6. .env.example Completado

```env
# Base de Datos
DATABASE_URL=postgresql+asyncpg://sentinel:sentinel_dev@localhost:5432/sentinelpy
POSTGRES_DB=sentinelpy
POSTGRES_USER=sentinel
POSTGRES_PASSWORD=sentinel_dev
POSTGRES_PORT=5432

# API
API_PORT=8000
SECRET_KEY=change-me-in-production
DEBUG=true

# Admin Seed
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

# Email
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
NOTIFY_TO=

# Webhook
WEBHOOK_URL=
NOTIFY_MIN_SEVERITY=high
```

**Diseño de las variables:**
- Nombres con mayúsculas y underscores (convención de 12factor)
- Sin prefijo `SENTINEL_` innecesario — el .env está dentro del proyecto
- Cada variable tiene un comentario explicativo
- Las opcionales van vacías por defecto

## Archivos Creados/Modificados

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `backend/Dockerfile` | Reescribito | Multi-stage builder+runtime, usuario no-root, entrypoint |
| `backend/scripts/docker-entrypoint.sh` | Creado | Ejecuta alembic upgrade head al iniciar |
| `docker-compose.yml` | Reescribito | Variables de entorno, healthchecks, logging, restart |
| `docker-compose.prod.yml` | Creado | Override productivo (sin puertos expuestos, DEBUG=false) |
| `backend/.env.example` | Reescribito | Completo con todas las variables del proyecto |
| `docs/guia-de-instalacion.md` | Creado | Guía paso a paso: dev, prod, notificaciones, troubleshooting |

## Modos de Uso

### Desarrollo

```bash
docker compose up -d
```

Usa los defaults del `.env` o las variables del entorno. La imagen se
construye desde el Dockerfile y las migraciones corren automáticamente.

### Producción

```bash
# 1. Configurar .env con valores seguros
# 2. Buildear y levantar
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

El override productivo:
- No expone PostgreSQL al host (seguridad)
- Desactiva DEBUG (no muestra stack traces al cliente)
- La imagen se buildéa sin hot-reload ni bind mounts

### Verificación

```bash
# Estado de los servicios
docker compose ps
# → ambos deben mostrar "healthy"

# Logs
docker compose logs -f api

# Healthcheck manual
curl http://localhost:8000/health
# → {"status":"healthy","app":"SentinelPy","version":"0.1.0",...}
```

## Lecciones Aprendidas

### 1. El patrón `exec "$@"` es crítico en entrypoints

Sin `exec`, el CMD del Dockerfile corre como subproceso del script shell.
Con `exec`, reemplaza al shell y se convierte en PID 1. Esto es importante
porque:

- `docker stop` envía SIGTERM al PID 1
- Sin `exec`, SIGTERM mata el shell pero no a uvicorn (proceso huérfano)
- Con `exec`, uvicorn recibe SIGTERM directamente y hace shutdown graceful

### 2. `--user` en pip + PATH

Cuando se usa `pip install --user` en el builder, los paquetes se instalan
en `/root/.local/lib/python3.13/site-packages`. El runtime necesita:

1. Copiar `/root/.local` completo (no solo site-packages, porque los
   scripts ejecutables también están ahí)
2. Setear `ENV PATH=/root/.local/bin:$PATH` para que los comandos
   (uvicorn, alembic) sean encontrados

### 3. Sintaxis `${VAR:-default}` de Docker Compose

Docker Compose v2 resuelve variables de entorno del archivo `.env` o del
entorno del shell. La sintaxis `${VAR:-default}` permite que el compose
funcione incluso sin `.env`:

```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-sentinel_dev}
```

Si `POSTGRES_PASSWORD` no está definida, usa `sentinel_dev`.
Si está definida en `.env`, usa ese valor.

### 4. Override compose vs. profile compose

Dos estrategias para separar dev/prod:

| Estrategia | Ventaja | Desventaja |
|-----------|---------|------------|
| **Override** (`-f prod.yml`) | Mergea configs, un solo archivo base | Dos comandos diferentes |
| **Profiles** (`--profile dev`) | Un solo comando, servicios selectivos | Más complejo de debuggear |

Elegí override porque es más explícito: el usuario ve exactamente qué
cambia entre dev y prod. Además, el archivo base ya tiene defaults
seguros, así que `docker compose up -d` solo funciona para dev sin
necesidad de profiles.

### 5. curl no está en python:3.13-slim

La imagen `python:3.13-slim` no incluye `curl`. El healthcheck:

```yaml
test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
```

Docker ejecuta el healthcheck desde el **host** (no dentro del contenedor).
Por lo tanto, no necesita que curl esté instalado en el contenedor — usa
el curl del sistema host o el engine de Docker.

### 6. La migración automática resuelve el problema de startup

Antes, al levantar el proyecto había que ejecutar manualmente:
```bash
alembic upgrade head
```

Si se olvidaba, la app mostraba errores de "tabla no existe". Ahora:

1. El contenedor arranca
2. El entrypoint ejecuta `alembic upgrade head`
3. Si las migraciones fallan, `set -e` detiene el contenedor
4. Docker reinicia según `restart: unless-stopped`
5. Cuando la DB está lista, las migraciones se aplican solas

## Próximos Pasos

- **HTTPS con Caddy / Nginx reverse proxy**
- **Backups automatizados de PostgreSQL**
- **Monitoreo con Prometheus + Grafana**
- **Despliegue en VPS con GitHub Actions + CI/CD**
- **Refactor frontend a React/TypeScript (N2)**
