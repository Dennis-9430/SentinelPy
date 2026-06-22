"""Punto de entrada de la aplicación FastAPI.

Configura la aplicación, registra rutas, middlewares,
y maneja el ciclo de vida (inicio/cierre).
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from app.config import settings
from app.api import events, rules, alerts
from app.services.pipeline import Pipeline

logger = logging.getLogger(__name__)

# ── Instancias globales del pipeline y colectores ───────────────────────
# Se inicializan en lifespan y se guardan como atributos de la app
pipeline = Pipeline()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el ciclo de vida de la aplicación.

    Al iniciar:
        - Crea las tablas en la base de datos (solo desarrollo)
        - Inicia el colector syslog UDP
        - Prepara el pipeline de procesamiento

    Al cerrar:
        - Detiene colectores gracefulmente
    """
    logger.info("Iniciando SentinelPy...")

    # ── Inicializar base de datos ────────────────────────────────────────
    try:
        from app.database import engine
        from app.models.base import Base

        # En desarrollo, crear tablas automáticamente
        # En producción se usan migraciones Alembic
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tablas de base de datos verificadas/creadas")
    except Exception as e:
        logger.warning("No se pudo conectar a la base de datos: %s", e)
        logger.warning("La API funcionará sin BD — los endpoints de datos devolverán error")

    # ── Iniciar colector syslog ──────────────────────────────────────────
    try:
        from app.services.collector import SyslogCollector

        colector = SyslogCollector(pipeline)
        await colector.start()
        app.state.colector = colector
        logger.info("Sistema de recolección iniciado")
    except Exception as e:
        logger.warning("No se pudo iniciar el colector syslog: %s", e)
        app.state.colector = None

    # ── Pipeline listo ───────────────────────────────────────────────────
    app.state.pipeline = pipeline
    logger.info("SentinelPy iniciado correctamente")

    yield  # La app corre durante este yield

    # ── Shutdown graceful ────────────────────────────────────────────────
    logger.info("Deteniendo SentinelPy...")

    if hasattr(app.state, "colector") and app.state.colector:
        await app.state.colector.stop()
        logger.info("Colectores detenidos")

    logger.info("SentinelPy detenido")


# ── Creación de la app FastAPI ──────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# ── Rutas de la API REST ────────────────────────────────────────────────
# Cada router se importa de app/api/ y se incluye con su prefijo
app.include_router(events.router)
app.include_router(rules.router)
app.include_router(alerts.router)

# ── Templates para la interfaz web (Jinja2) ─────────────────────────────
# En Nivel 1 usamos server-side rendering con Jinja2 + Tailwind
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Página principal del dashboard.

    Muestra cards con métricas (eventos hoy, alertas activas, reglas)
    y la tabla de eventos recientes.
    """
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "app_name": settings.app_name},
    )


@app.get("/health")
async def health():
    """Endpoint de health check.

    Usado por Docker Compose y orquestadores para verificar
    que la aplicación responde correctamente.
    """
    return {"status": "healthy", "app": settings.app_name, "version": settings.app_version}
