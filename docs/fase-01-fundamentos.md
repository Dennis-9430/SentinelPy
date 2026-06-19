# Fase 01: Fundamentos y Estructura del Proyecto

## Objetivo

Establecer la base del proyecto SentinelPy: estructura de directorios, configuración inicial,
modelos de datos, y primer endpoint funcional.

## Stack Definido

| Componente | Tecnología |
|------------|-----------|
| Backend     | Python 3.13+ |
| Framework   | FastAPI |
| Base de datos | PostgreSQL 16 |
| ORM | SQLAlchemy 2.0 (asíncrono) |
| Migraciones | Alembic |
| Frontend N1 | Jinja2 + Tailwind CSS |
| Contenedores | Docker + Docker Compose |

## Decisiones Técnicas

### 1. SQLAlchemy asíncrono con asyncpg

Usamos el driver `asyncpg` en lugar de `psycopg2` porque FastAPI es asíncrono y
bloquear el event loop con queries sync mata la performance.

### 2. Modelo de Datos

Tres entidades principales:

- **NormalizedEvent**: un log normalizado (origen, tipo, severidad, IPs, etc.)
- **DetectionRule**: una regla de detección estilo Sigma (título, condiciones, severidad)
- **Alert**: una alerta generada cuando una regla matchea uno o más eventos

### 3. Arquitectura en Capas

```
api/       → endpoints HTTP (thin)
schemas/   → validación Pydantic (request/response)
services/  → lógica de negocio (colectores, parser, engine)
models/    → SQLAlchemy models (base de datos)
```

Las capas dependen hacia adentro: `api → services → models`.

## Estructura del Proyecto

```
backend/
├── app/
│   ├── api/          # Rutas FastAPI
│   ├── models/       # SQLAlchemy ORM
│   ├── schemas/      # Pydantic
│   ├── services/     # Lógica de negocio
│   └── main.py       # Entry point
├── alembic/          # Migraciones
├── tests/            # Tests
├── requirements.txt
└── Dockerfile
docker-compose.yml
docs/
README.md
```

## Lo que Aprendí

- **SQLAlchemy 2.0 async**: la sintaxis con `Mapped` y `mapped_column` es más limpia
  que la version anterior. Configurar el engine con `create_async_engine` y session
  con `async_sessionmaker`.
- **Pydantic v2**: `model_config` reemplaza `Config` interno. `from_attributes` para
  ORM mode.
- **FastAPI lifespan**: reemplaza los viejos eventos `startup/shutdown`.
- **UUID como PK**: usar `uuid.uuid4` como default evita ataques de enumeración.

## Próximos Pasos (Fase 02)

- Implementar colector syslog (UDP)
- Implementar parser syslog RFC 3164
- Conectar PostgreSQL con Docker Compose y correr primera migración
