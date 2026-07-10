# Guía de Instalación de SentinelPy

## Requisitos

- Docker y Docker Compose v2
- Git
- Puerto 8000 libre (API) y 5432 libre (PostgreSQL)

## Instalación Rápida (Desarrollo)

```bash
# 1. Clonar el repositorio
git clone https://github.com/Dennis-9430/SentinelPy.git
cd SentinelPy

# 2. Configurar entorno (opcional — los defaults funcionan para dev)
cp backend/.env.example .env
# Editar .env si es necesario

# 3. Levantar los servicios
docker compose up -d

# 4. Abrir el dashboard
# http://localhost:8000
# Usuario: admin / Contraseña: admin123
```

## Instalación para Producción

```bash
# 1. Generar secret key
# Linux/Mac:
#   openssl rand -hex 32
# Windows PowerShell:
#   [System.Convert]::ToHexString((1..32 | ForEach-Object { Get-Random -Max 256 }))

# 2. Configurar .env con valores seguros
cat > .env << EOF
SECRET_KEY=tu-secreto-generado-aqui-de-32-bytes
POSTGRES_PASSWORD=contraseña-segura-postgres
DEBUG=false
ADMIN_PASSWORD=contraseña-segura-admin
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alertas@tuempresa.com
SMTP_PASSWORD=contraseña-de-aplicacion
NOTIFY_TO=analistas@tuempresa.com
EOF

# 3. Levantar en modo producción
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 4. Verificar healthcheck
curl http://localhost:8000/health
```

## Datos de demostración

Una vez que los contenedores estén corriendo (`docker compose up -d`), ejecutá el seed script para poblar la base de datos con datos de ejemplo:

```bash
# Ejecutar seed script
docker compose exec api python scripts/seed_demo_data.py

# Reiniciar API para que recargue las reglas
docker compose restart api
```

Esto genera:
- **7 reglas** de correlación (6 activas + 1 deshabilitada)
- **150 eventos** de prueba distribuidos en las últimas 24 horas
- **~20 alertas** en distintos estados

### Agentes remotos (demo)

El `docker-compose.yml` incluye un agente demo que monitorea archivos de log en `demo-logs/`:

```bash
# El agente se inicia automáticamente con docker compose up -d
# Ver logs del agente:
docker compose logs -f agent
```

Los archivos de demo en `demo-logs/` contienen logs de ejemplo (syslog, JSON) que el agente envía al servidor.

## Configuración de Notificaciones

### Email (Gmail)

1. Activar verificación en dos pasos en tu cuenta de Google
2. Generar contraseña de aplicación en: https://myaccount.google.com/apppasswords
3. Configurar en .env:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=tu-email@gmail.com
   SMTP_PASSWORD=la-contraseña-de-aplicacion
   NOTIFY_TO=["analista1@ejemplo.com", "analista2@ejemplo.com"]
   ```

### Slack

1. Ir a Slack API → Crear app → Webhooks entrantes
2. Obtener URL del webhook
3. Configurar en .env:
   ```
   WEBHOOK_URL=https://hooks.slack.com/services/T00/B00/xxxxx
   ```

### Discord

1. Ir a Configuración del canal → Integraciones → Webhooks
2. Crear webhook y copiar URL
3. Configurar en .env:
   ```
   WEBHOOK_URL=https://discord.com/api/webhooks/xxxxx/yyyyy
   ```

## Comandos Útiles

| Comando | Descripción |
|---------|-------------|
| `docker compose up -d` | Iniciar en modo desarrollo |
| `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` | Iniciar en modo producción |
| `docker compose logs -f api` | Ver logs de la API en tiempo real |
| `docker compose logs -f db` | Ver logs de PostgreSQL |
| `docker compose down` | Detener servicios (no borra datos) |
| `docker compose down -v` | Detener y borrar volúmenes (⚠️ borra datos) |
| `docker compose build --no-cache api` | Reconstruir imagen sin cache |
| `curl http://localhost:8000/health` | Healthcheck |
| `docker compose logs -f agent` | Ver logs del agente remoto |
| `docker compose exec api python scripts/seed_demo_data.py` | Poblar datos de demostración |
| `cd backend && pytest -v` | Ejecutar tests del backend |
| `cd frontend && pnpm test` | Ejecutar tests del frontend |
| `cd frontend && pnpm build` | Compilar frontend para producción |

## Estructura de Archivos

```
SentinelPy/
├── backend/
│   ├── app/
│   │   ├── api/          # Routers (events, rules, alerts, auth, users, agents, analysis)
│   │   ├── models/       # SQLAlchemy models (Event, Rule, Alert, User, Agent)
│   │   ├── services/     # Business logic (engine, pipeline, analysis, ML, notifiers)
│   │   ├── config.py     # Settings con pydantic-settings
│   │   ├── database.py   # async engine + session factory
│   │   ├── main.py       # FastAPI app + lifespan + SPA catch-all
│   │   └── auth.py       # JWT helpers
│   ├── alembic/          # Database migrations
│   ├── tests/            # Backend tests (unit + integration)
│   ├── scripts/
│   │   ├── seed_demo_data.py    # Demo data seeder
│   │   └── docker-entrypoint.sh # Container entrypoint
│   ├── Dockerfile        # Multi-stage image
│   └── requirements.txt  # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── pages/        # 6 pages (Login, Dashboard, Events, Alerts, Rules, Users)
│   │   ├── components/   # UI components (SeverityBadge, RiskBadge, AlertGroup, shadcn/ui)
│   │   ├── hooks/        # useAuth (AuthProvider)
│   │   ├── lib/          # api.ts, types.ts, utils.ts
│   │   └── router.tsx    # React Router v7 with lazy loading
│   ├── package.json
│   └── vite.config.ts    # Vite + Vitest config
├── agent/
│   ├── agent.py          # Main agent entry point
│   ├── watcher.py        # File watcher (polls for changes)
│   ├── sender.py         # Batch sender to API (httpx)
│   ├── queue.py          # SQLite-backed queue
│   ├── parsers.py        # Log parsers (syslog, JSON, regex)
│   ├── config.py         # TOML config loader
│   ├── config.toml       # Agent configuration
│   ├── Dockerfile        # Agent container
│   ├── requirements.txt  # Agent dependencies
│   └── tests/            # Agent tests
├── demo-logs/            # Demo log files for agent testing
├── openspec/             # SDD artifacts (specs, designs, tasks)
├── docker-compose.yml        # Development
├── docker-compose.prod.yml   # Production override
└── docs/                     # Documentation
```

## Testing

### Backend

```bash
cd backend

# Ejecutar todos los tests
pytest -v

# Tests específicos
pytest tests/test_analysis_service.py -v    # Analysis service
pytest tests/test_ml_engine.py -v           # ML engine
pytest tests/test_alert_grouping.py -v      # Alert grouping

# Con coverage
pytest --cov=app --cov-report=term-missing
```

Los tests de integración usan **testcontainers** — levantan una PostgreSQL temporal automáticamente.

### Frontend

```bash
cd frontend

# Ejecutar tests
pnpm test

# Watch mode
pnpm test:watch

# Type check
npx tsc --noEmit

# Build
pnpm build
```

### Agent

```bash
cd agent

# Ejecutar tests
pytest -v
```

## Solución de Problemas

### Error de conexión a la base de datos

```bash
# Verificar que PostgreSQL está corriendo
docker compose ps

# Ver logs de PostgreSQL
docker compose logs db

# Si PostgreSQL no arranca, puede ser un problema de versión:
# Probar reiniciando Docker Desktop
```

### Error de puerto en uso

```bash
# Verificar qué está usando el puerto
# PowerShell:
netstat -ano | findstr :8000
netstat -ano | findstr :5432

# Cambiar puerto en .env:
# API_PORT=8001
# POSTGRES_PORT=5433
```

### Las migraciones no se aplican

Las migraciones se ejecutan automáticamente al iniciar el contenedor vía
el entrypoint script. Si fallan:

```bash
# Ver logs de la API
docker compose logs api

# Si es necesario, ejecutar migraciones manualmente:
docker compose exec api alembic upgrade head
```

## Próximos Pasos

- Monitoreo con Prometheus + Grafana
- Respaldo automatizado de la base de datos
- HTTPS con Let's Encrypt + reverse proxy (Caddy / Nginx)
- Dashboard de métricas del agente (latencia, eventos/segundo, errores)
